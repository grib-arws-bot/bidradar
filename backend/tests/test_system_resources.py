"""서버 자원 사용량(2026-09-12) — app/services/system_resources.py 검증. 실제 /proc·cgroup
파일에 의존하지 않는다(개발 PC는 Windows라 애초에 이 경로들이 없음) — 계산 로직은 순수
함수로 직접 검증하고, get_system_resources() 전체 흐름은 파일 읽기를 모킹해서 확인한다."""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from app.services.system_resources import (
    _compute_container_cpu_percent,
    _compute_host_cpu_percent,
    get_system_resources,
)


def test_compute_host_cpu_percent_typical():
    # idle이 델타의 90%면 사용률은 10%
    assert _compute_host_cpu_percent(idle_delta=900, total_delta=1000) == 10.0


def test_compute_host_cpu_percent_fully_idle():
    assert _compute_host_cpu_percent(idle_delta=1000, total_delta=1000) == 0.0


def test_compute_host_cpu_percent_guards_zero_division():
    assert _compute_host_cpu_percent(idle_delta=0, total_delta=0) == 0.0


def test_compute_container_cpu_percent_one_full_core_of_four():
    # 4코어 중 1코어를 꽉 채워 썼으면 전체 용량 대비 25%
    elapsed_usec = 1_000_000  # 1초
    usec_delta = 1_000_000  # 그 1초 동안 CPU 시간 1초어치를 씀(코어 1개 풀가동)
    assert _compute_container_cpu_percent(usec_delta, elapsed_usec, num_cores=4) == 25.0


def test_compute_container_cpu_percent_idle():
    assert _compute_container_cpu_percent(0, 1_000_000, num_cores=4) == 0.0


_PROC_STAT_LOW = "cpu  100 0 100 800 0 0 0 0 0 0\n"
_PROC_STAT_HIGH = "cpu  200 0 100 800 0 0 0 0 0 0\n"  # user만 100 늘고 idle은 그대로 -> 사용률 증가
_CGROUP_CPU_STAT = "usage_usec 5000000\nuser_usec 4000000\nsystem_usec 1000000\n"
_MEMINFO = "MemTotal:       8000000 kB\nMemAvailable:   4000000 kB\n"


def test_get_system_resources_full_flow():
    """실제 파일을 못 읽는 개발 PC에서도 전체 계산 흐름(파일 파싱 -> 퍼센트 계산 -> 응답 조립)
    이 맞는지 확인 — open()을 경로별로 다르게 응답하도록 모킹한다."""
    call_count = {"proc_stat": 0, "cgroup_cpu": 0}

    def fake_open(path, *args, **kwargs):
        if path == "/proc/stat":
            call_count["proc_stat"] += 1
            content = _PROC_STAT_LOW if call_count["proc_stat"] == 1 else _PROC_STAT_HIGH
            return mock.mock_open(read_data=content)()
        if path == "/sys/fs/cgroup/cpu.stat":
            call_count["cgroup_cpu"] += 1
            return mock.mock_open(read_data=_CGROUP_CPU_STAT)()
        if path == "/proc/meminfo":
            return mock.mock_open(read_data=_MEMINFO)()
        if path == "/sys/fs/cgroup/memory.current":
            return mock.mock_open(read_data="123456789\n")()
        if path == "/sys/fs/cgroup/memory.max":
            return mock.mock_open(read_data="max\n")()
        raise AssertionError(f"예상 못 한 경로가 열림: {path}")

    with mock.patch("builtins.open", side_effect=fake_open), mock.patch(
        "app.services.system_resources.time.sleep"
    ), mock.patch("app.services.system_resources.os.cpu_count", return_value=4), mock.patch(
        "app.services.system_resources.shutil.disk_usage",
        return_value=mock.Mock(total=100_000_000_000, used=24_200_000_000, free=75_800_000_000),
    ):
        result = get_system_resources()

    assert result["available"] is True
    assert result["cpu"]["cores"] == 4
    assert result["cpu"]["host_percent"] > 0  # user 틱이 늘었으니 0%가 아니어야 함
    assert result["memory"]["host_total_bytes"] == 8_000_000 * 1024
    assert result["memory"]["host_used_bytes"] == (8_000_000 - 4_000_000) * 1024
    assert result["memory"]["container_used_bytes"] == 123456789
    assert result["memory"]["container_limit_bytes"] is None  # "max" -> 무제한
    assert result["disk"]["host_total_bytes"] == 100_000_000_000
    assert result["disk"]["host_percent"] == 24.2


def test_get_system_resources_returns_unavailable_when_files_missing():
    """개발 PC(Windows, 컨테이너 밖)에서 실제로 겪는 상황 — /proc·cgroup이 아예 없다.
    조용히 빈 값으로 위장하지 않고 available=False + 이유를 그대로 알려줘야 한다."""
    with mock.patch("builtins.open", side_effect=FileNotFoundError("No such file or directory")):
        result = get_system_resources()
    assert result["available"] is False
    assert "error" in result
