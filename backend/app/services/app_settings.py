"""범용 앱 설정 CRUD(2026-09-12) — key-value. 타입별 접근은 이 파일에 헬퍼로 추가한다
(예: get_report_retention_days). 화면은 지금은 "보고서 관리" 페이지 상단 하나뿐이지만,
설정이 늘어나면 이 서비스와 app/api/settings.py의 GET/PUT 하나로 계속 대응한다."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection

from app.models import app_setting

# 보고서 자동 삭제 보관기간(일) — None/미설정이면 자동 삭제 안 함(2026-09-12 사용자 지시,
# "생성 후 N일 지나면 자동 삭제"). interest_report.generate_report()가 매번 이 값을 확인해
# 만료된 리포트를 정리한다(app/services/notice_cleanup.py의 "수집 시 자동 정리"와 같은 방식
# — 별도 스케줄러 없이 기존 트리거에 얹는다).
REPORT_RETENTION_DAYS_KEY = "report_retention_days"


def get_setting(conn: Connection, key: str, default=None):
    row = conn.execute(select(app_setting.c.value).where(app_setting.c.key == key)).first()
    return row[0] if row else default


def set_setting(conn: Connection, key: str, value) -> None:
    stmt = insert(app_setting).values(key=key, value=value, updated_at=func.now())
    stmt = stmt.on_conflict_do_update(index_elements=[app_setting.c.key], set_={"value": stmt.excluded.value, "updated_at": func.now()})
    conn.execute(stmt)


def get_report_retention_days(conn: Connection) -> int | None:
    return get_setting(conn, REPORT_RETENTION_DAYS_KEY, default=None)


def set_report_retention_days(conn: Connection, days: int | None) -> None:
    if days is not None and days < 1:
        raise ValueError("보관기간은 1일 이상이어야 합니다.")
    set_setting(conn, REPORT_RETENTION_DAYS_KEY, days)
