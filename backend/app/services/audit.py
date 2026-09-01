"""관리자 동작 감사 로그(CLAUDE.md 코드 규칙 — 소스·키워드·사용자 변경은 여기로 기록).

단일 공유 계정(의사결정_로그 9번)이라 actor는 사실상 항상 report@grib.co.kr로 고정된다 —
개인별 구분이 안 되는 건 알려진 트레이드오프로 수용(같은 로그 항목 참고).
"""

from __future__ import annotations

from sqlalchemy import insert
from sqlalchemy.engine import Connection

from app.models import audit_log


def record(
    conn: Connection,
    *,
    actor: str,
    action: str,
    target_type: str,
    target_id: str | int | None = None,
    detail: dict | None = None,
) -> None:
    conn.execute(
        insert(audit_log).values(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            detail=detail,
        )
    )
