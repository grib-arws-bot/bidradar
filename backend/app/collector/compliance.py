"""분기별 준법 재확인(advisory INBOX #6, 2026-09-01) — robots.txt·이용약관은 사전 통보 없이
바뀔 수 있으므로, 소스 등록 시 1회 확인으로 끝내지 않고 주기적으로 다시 읽어 변경을 감지한다.

자동 스케줄링(APScheduler)은 아직 인프라가 없어(설계안 스택 표에만 있고 미구축 상태) 이
모듈은 검사 로직만 제공한다 — 지금은 `python -m app.cli check-compliance`로 수동 실행하고,
스케줄러가 생기면 그 잡이 이 함수를 그대로 호출하면 된다.

A등급(이용허락범위 "제한 없음")은 근거가 robots.txt가 아니라 공공데이터법상 이용허락범위라
robots 변경과 무관하다 — 재확인 대상은 B·C 등급만(로그인·크롤링 접근성에 등급이 좌우되는
소스들).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from app.models import audit_log, source
from app.security import url_guard


def _robots_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def check_source(conn: Connection, source_id: int) -> dict:
    """소스 하나의 robots.txt를 다시 읽어 이전에 저장해둔 해시와 비교한다. 바뀌었으면 소스를
    비활성화하고 audit_log에 남긴다 — 사람이 다시 검토하기 전엔 수집을 재개하지 않는다(안전
    쪽으로 기운다, 조용히 계속 도는 것보다 낫다)."""
    src = conn.execute(select(source).where(source.c.id == source_id)).mappings().first()
    if src is None:
        raise ValueError(f"소스를 찾을 수 없습니다: {source_id}")

    robots_url = _robots_url(src["base_url"])
    new_hash: str | None = None
    error: str | None = None
    try:
        response = url_guard.fetch(robots_url)
        new_hash = hashlib.sha256(response.content).hexdigest()
    except Exception as exc:  # noqa: BLE001 — robots.txt가 없는 사이트도 있어 실패=이상 신호는 아님
        error = str(exc)

    now = datetime.now(timezone.utc)
    changed = new_hash is not None and src["robots_hash"] is not None and new_hash != src["robots_hash"]

    values: dict = {"legal_verified_at": now}
    if new_hash is not None:
        values["robots_hash"] = new_hash
    if changed:
        values["active"] = False
    conn.execute(update(source).where(source.c.id == source_id).values(**values))

    if changed:
        conn.execute(
            insert(audit_log).values(
                actor="system.compliance_check",
                action="source.compliance_alert",
                target_type="source",
                target_id=str(source_id),
                detail={
                    "note": "robots.txt 변경 감지 — 자동 비활성화됨. 재검토 후 관리자가 다시 활성화해야 합니다.",
                    "old_hash": src["robots_hash"],
                    "new_hash": new_hash,
                },
            )
        )

    return {
        "source_id": source_id,
        "name": src["name"],
        "fetch_ok": new_hash is not None,
        "changed": changed,
        "checked_at": now.isoformat(),
        "error": error,
    }


def check_all_sources(conn: Connection) -> list[dict]:
    ids = conn.execute(select(source.c.id).where(source.c.legal_tier.in_(("B", "C")))).scalars().all()
    return [check_source(conn, source_id) for source_id in ids]
