"""소스 목록 — 관리자 페이지 "소스 관리"용 읽기 전용 조회(2026-09-01 요청).

전체 CRUD(등록·probe·suggest-map·dryrun·rollback, 구현스펙 03절 `/api/admin/sources`)는
아직 없음 — 지금은 현재 연동된 소스를 기관별로 한눈에 보는 목록만 제공한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from app.collector.runner import RUNNING_STALE_MINUTES
from app.models import source, source_run
from app.services.notice_classification import notice_type_of

ADAPTER_LABELS = {"openapi": "오픈API", "feed": "피드", "html": "HTML 크롤링"}
# 마지막 준법 확인일로부터 이만큼 지나면 S5 화면에 경고 배지(advisory INBOX #6, 분기 재확인 주기)
COMPLIANCE_WARNING_DAYS = 90

# 소스명 접두어 → 공고기관(채널) 표시명(2026-09-05, 공고 탐색 필터 재구성). 새 채널을 추가할
# 소스를 등록할 때는 이 목록도 같이 갱신해야 한다 — 안 그러면 org_name으로 조용히 대체된다
# (아래 derive_channel_name 참고, "조용한 오분류" 방지를 위해 매칭 실패도 org_name이라는
# 눈에 보이는 값으로 떨어지게 함).
CHANNEL_NAME_PREFIXES = ("나라장터", "IRIS", "K-water", "과학기술정보통신부")


def derive_channel_name(source_name: str, org_name: str | None) -> str:
    for prefix in CHANNEL_NAME_PREFIXES:
        if source_name.startswith(prefix):
            return prefix
    return org_name or source_name


def list_sources(conn: Connection) -> list[dict]:
    """기관명 → 소스명 순으로 정렬된 전체 소스 목록. 각 소스의 최근 수집 상태·시각을 붙인다."""
    latest_run_sq = (
        select(source_run.c.source_id, func.max(source_run.c.id).label("latest_id"))
        .group_by(source_run.c.source_id)
        .subquery()
    )
    rows = conn.execute(
        select(
            source.c.id,
            source.c.name,
            source.c.org_name,
            source.c.channel_name,
            source.c.homepage_url,
            source.c.adapter_type,
            source.c.stage,
            source.c.active,
            source.c.legal_tier,
            source.c.legal_verified_at,
            source.c.auto_extract,
            source.c.auto_analyze,
            source.c.schedule_times,
            source_run.c.status,
            source_run.c.run_at,
            source_run.c.duration_ms,
        )
        .select_from(source)
        .join(latest_run_sq, latest_run_sq.c.source_id == source.c.id, isouter=True)
        .join(source_run, source_run.c.id == latest_run_sq.c.latest_id, isouter=True)
        .order_by(source.c.org_name, source.c.name)
    ).mappings().all()

    now = datetime.now(timezone.utc)
    result = []
    for row in rows:
        status = row["status"] if row["active"] else "inactive"
        if status is None:
            status = "no_run_yet"
        # 'running' 표시는 프론트가 "지금 수집" 버튼을 비활성화하는 신호로 쓴다(2026-09-08,
        # 사용자 발견 — 클릭 후 다른 메뉴로 갔다 돌아오면 이미 끝난 것처럼 보이던 문제). 다만
        # 프로세스가 죽어서 영원히 'running'으로 남을 수 있어(하트비트 없음), 이 시간을 넘긴
        # 행은 화면에서만이라도 "실패"로 보여준다 — 실제 행 정리는 다음 수집 시도 때
        # _reject_if_already_running()이 한다.
        if status == "running" and row["run_at"] and (now - row["run_at"]) > timedelta(minutes=RUNNING_STALE_MINUTES):
            status = "fail"
        verified_at = row["legal_verified_at"]
        compliance_overdue = verified_at is None or (now - verified_at) > timedelta(days=COMPLIANCE_WARNING_DAYS)
        result.append(
            {
                "id": row["id"],
                "name": row["name"],
                "org_name": row["org_name"],
                "homepage_url": row["homepage_url"],
                "adapter_type": row["adapter_type"],
                "adapter_label": ADAPTER_LABELS.get(row["adapter_type"], row["adapter_type"]),
                "stage": row["stage"],
                "status": status,
                "last_run_at": row["run_at"].isoformat() if row["run_at"] else None,
                "legal_tier": row["legal_tier"],
                "legal_verified_at": verified_at.isoformat() if verified_at else None,
                "compliance_overdue": compliance_overdue,
                "auto_extract": row["auto_extract"],
                "auto_analyze": row["auto_analyze"],
                "active": row["active"],
                "notice_type": notice_type_of(row["channel_name"]),
                "schedule_times": row["schedule_times"] or [],
                # 최근 1회 수집(+첨부분석·AI분석까지 포함한 전체) 소요시간(ms) — "공고 업데이트
                # 시간"을 서로 안 겹치게 잡으려면 실제로 얼마나 걸리는지 알아야 한다(2026-09-14
                # 사용자 요청으로 신설, app/collector/runner.py run_source_and_process_pending에서
                # 측정). 과거 실행분은 값이 없을 수 있다(이 기능 추가 이전 기록).
                "last_duration_ms": row["duration_ms"],
            }
        )
    return result


def set_auto_extract(conn: Connection, source_id: int, enabled: bool) -> bool:
    """소스가 존재해 실제로 값이 바뀌었으면 True, 없는 source_id면 False."""
    result = conn.execute(source.update().where(source.c.id == source_id).values(auto_extract=enabled))
    return result.rowcount > 0


def set_active(conn: Connection, source_id: int, enabled: bool) -> bool:
    """공고 자동 수집 on/off(2026-09-05, 관리자 화면에 노출) — 꺼두면 이 소스는 더 이상
    수집하지 않는다(app/collector/runner.py는 이 값과 무관하게 호출될 수 있으므로, 실제
    스케줄러/자동화가 붙을 때 이 플래그를 반드시 확인해야 함)."""
    result = conn.execute(source.update().where(source.c.id == source_id).values(active=enabled))
    return result.rowcount > 0


def set_auto_analyze(conn: Connection, source_id: int, enabled: bool) -> bool:
    """A2(LLM, 비용 발생) 자동 실행 on/off(2026-09-05) — auto_extract 성공 직후 Haiku로
    자동 구조화까지 실행할지. 관리자가 이 화면에서 명시적으로 켜는 설정이라 CLAUDE.md
    "자동 실행 금지" 원칙과 충돌하지 않는다고 판단(사용자 확정)."""
    result = conn.execute(source.update().where(source.c.id == source_id).values(auto_analyze=enabled))
    return result.rowcount > 0


class ScheduleTimesError(ValueError):
    pass


def validate_schedule_times(times: list[str]) -> None:
    """"HH:MM" 최대 3개, 00:00~23:59 범위(2026-09-07 — 드롭다운 3칸 대신 직접 입력으로
    바뀌면서 5분 단위 제한은 뺌. 실행 엔진은 아직 없고 설정값만 저장하지만, 나중에 그
    엔진이 그대로 신뢰하고 쓸 수 있도록 저장 시점에 형식을 강제한다."""
    if len(times) > 3:
        raise ScheduleTimesError("공고 업데이트 시간은 최대 3개까지 설정할 수 있습니다.")
    for t in times:
        try:
            hour_str, minute_str = t.split(":")
            hour, minute = int(hour_str), int(minute_str)
        except (ValueError, AttributeError) as exc:
            raise ScheduleTimesError(f"시간 형식이 올바르지 않습니다(HH:MM, 00:00~23:59): {t!r}") from exc
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            raise ScheduleTimesError(f"시간은 00:00~23:59 범위여야 합니다: {t!r}")


def set_schedule_times(conn: Connection, source_id: int, times: list[str]) -> bool:
    validate_schedule_times(times)
    result = conn.execute(source.update().where(source.c.id == source_id).values(schedule_times=times))
    return result.rowcount > 0
