"""서버 자원 사용량(2026-09-12, 전체 현황 "시스템 현황" 카드) — ARWS(D:\\Code-CLI\\ARWS
backend/server.js:3716-3874)와 같은 방식을 그대로 이식한다.

**Docker 소켓은 안 쓴다** — ARWS도 백엔드에 root급 권한을 주는 위험 때문에 명시적으로
배제했다(같은 서버의 infra/collect-arws-usage.sh 참고, 호스트 cron이 대신 집계). BidRadar는
자기 컨테이너 하나만 보면 되므로 그 배제조차 필요 없이, cgroup v2 파일을 컨테이너 안에서
직접 읽는 것만으로 충분하다(2026-09-12 실제 prod 컨테이너에서 `/sys/fs/cgroup/cpu.stat`·
`memory.current`·`memory.max` 접근 가능 확인).

`os.cpus()`(Node)나 `psutil`(Python) 둘 다 **호스트 전체** 값만 주고 컨테이너 스코프 인식이
없다는 게 ARWS 조사에서 나온 핵심 함정 — "서버 전체"와 "backend 자체"는 출처가 다른 두
계산이다(host: /proc/stat·/proc/meminfo, container: cgroup 파일)."""

from __future__ import annotations

import os
import shutil
import time

_PROC_STAT = "/proc/stat"
_PROC_MEMINFO = "/proc/meminfo"
_CGROUP_CPU_STAT = "/sys/fs/cgroup/cpu.stat"
_CGROUP_MEM_CURRENT = "/sys/fs/cgroup/memory.current"
_CGROUP_MEM_MAX = "/sys/fs/cgroup/memory.max"

# CPU는 순간값이 아니라 두 시점 사이의 델타로 계산해야 한다(둘 다 누적 카운터) — ARWS도
# 같은 이유로 롤링 샘플을 쓴다. 요청마다 짧게 대기하는 것으로 대신한다(이 엔드포인트는
# 대시보드 최초 로드시 1회만 호출되고 폴링하지 않음, ARWS와 동일 패턴).
_CPU_SAMPLE_INTERVAL_SECONDS = 0.3


def _read_proc_stat_cpu_ticks() -> tuple[int, int]:
    """/proc/stat 첫 줄(전체 코어 합산) — (idle_ticks, total_ticks)."""
    with open(_PROC_STAT) as f:
        first_line = f.readline()
    # "cpu  user nice system idle iowait irq softirq steal guest guest_nice"
    parts = [int(p) for p in first_line.split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)  # idle + iowait
    total = sum(parts)
    return idle, total


def _read_cgroup_cpu_usage_usec() -> int:
    with open(_CGROUP_CPU_STAT) as f:
        for line in f:
            key, value = line.split()
            if key == "usage_usec":
                return int(value)
    raise RuntimeError("cpu.stat에서 usage_usec을 찾지 못했습니다")


def _compute_host_cpu_percent(idle_delta: int, total_delta: int) -> float:
    if total_delta <= 0:
        return 0.0
    return round((1 - idle_delta / total_delta) * 100, 1)


def _compute_container_cpu_percent(usec_delta: int, elapsed_usec: float, num_cores: int) -> float:
    return round((usec_delta / (elapsed_usec * num_cores)) * 100, 1)


def _cpu_percentages(num_cores: int) -> tuple[float, float]:
    """(host_percent, container_percent) — 전체 시스템 용량(모든 코어) 대비 비율로 통일해서
    ARWS 화면의 "서버 전체" 대비 "backend 자체" 비교가 말이 되게 한다."""
    host_idle_1, host_total_1 = _read_proc_stat_cpu_ticks()
    container_usec_1 = _read_cgroup_cpu_usage_usec()
    time.sleep(_CPU_SAMPLE_INTERVAL_SECONDS)
    host_idle_2, host_total_2 = _read_proc_stat_cpu_ticks()
    container_usec_2 = _read_cgroup_cpu_usage_usec()

    host_percent = _compute_host_cpu_percent(host_idle_2 - host_idle_1, host_total_2 - host_total_1)
    container_percent = _compute_container_cpu_percent(
        container_usec_2 - container_usec_1, _CPU_SAMPLE_INTERVAL_SECONDS * 1_000_000, num_cores
    )
    return host_percent, container_percent


def _read_meminfo() -> tuple[int, int]:
    """(total_bytes, available_bytes) — MemAvailable은 캐시 회수 가능분까지 감안한 값이라
    MemFree보다 "실제로 쓸 수 있는 여유"에 가깝다(리눅스 커널 문서 권장 지표)."""
    values = {}
    with open(_PROC_MEMINFO) as f:
        for line in f:
            key, rest = line.split(":", 1)
            if key in ("MemTotal", "MemAvailable"):
                values[key] = int(rest.strip().split()[0]) * 1024  # kB -> bytes
    return values["MemTotal"], values["MemAvailable"]


def _read_cgroup_memory() -> tuple[int, int | None]:
    with open(_CGROUP_MEM_CURRENT) as f:
        used = int(f.read().strip())
    with open(_CGROUP_MEM_MAX) as f:
        raw_max = f.read().strip()
    limit = None if raw_max == "max" else int(raw_max)
    return used, limit


def get_system_resources() -> dict:
    """이 엔드포인트는 폴링하지 않고 화면 진입 시 1회만 호출된다(ARWS와 동일 패턴) —
    CPU 측정에 짧은 sleep이 들어가 응답이 약간 느릴 수 있으나(0.3초) 그 정도는 괜찮다.

    /proc·cgroup 파일은 리눅스에서만, 그것도 cgroup v2일 때만 있다 — 개발 PC에서 pytest를
    직접 돌릴 때(컨테이너 밖, Windows)는 당연히 없다. 조용히 빈 값으로 위장하지 않고
    "이 환경에서는 못 가져왔다"는 사실 자체를 error 필드에 남긴다(CLAUDE.md 조용한 실패
    금지)."""
    try:
        num_cores = os.cpu_count() or 1
        cpu_host_percent, cpu_container_percent = _cpu_percentages(num_cores)

        mem_total, mem_available = _read_meminfo()
        mem_used = mem_total - mem_available
        mem_container_used, mem_container_limit = _read_cgroup_memory()

        disk_usage = shutil.disk_usage("/")
    except OSError as exc:
        return {"available": False, "error": f"서버 자원 정보를 읽을 수 없습니다({exc}) — 리눅스·cgroup v2 환경에서만 지원합니다."}

    return {
        "available": True,
        "cpu": {"cores": num_cores, "host_percent": cpu_host_percent, "container_percent": cpu_container_percent},
        "memory": {
            "host_percent": round(mem_used / mem_total * 100, 1),
            "host_used_bytes": mem_used,
            "host_total_bytes": mem_total,
            "container_used_bytes": mem_container_used,
            "container_limit_bytes": mem_container_limit,
        },
        # 디스크는 ARWS도 host 기준만 제공한다 — 컨테이너 전용 쓰기 계층(overlay2) 사용량은
        # cgroup에 별도 집계가 없어 host df와 동일하게 둘 다 같은 값을 쓴다.
        "disk": {
            "host_percent": round(disk_usage.used / disk_usage.total * 100, 1),
            "host_used_bytes": disk_usage.used,
            "host_total_bytes": disk_usage.total,
        },
    }
