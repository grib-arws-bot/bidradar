"""발주기관(org) 중심 목록 — 관리자 페이지 "소스 관리" 실제 표시 대상(2026-09-01 요청).

"조달청·IRIS는 실제 발주기관이 아니라 공고기관(채널)이다"라는 지적에 따라, 화면은
발주기관(org)을 기준으로 구성하고 그 기관이 어느 채널(소스)로 수집되는지를 붙여
보여준다. source_registry.list_sources()는 채널 자체의 상태를 보는 별도 용도로 남긴다.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.engine import Connection

from app.models import org, source, source_run
from app.services.source_registry import ADAPTER_LABELS, COMPLIANCE_WARNING_DAYS

_HANGUL_RE = re.compile(r"^[가-힣]")


def _sort_key(name: str) -> tuple[int, str]:
    # 한글순 먼저, 그다음 영어(그 외 문자)순 — DB 콜레이션에 기대지 않고 여기서 직접 정렬한다
    return (0 if _HANGUL_RE.match(name) else 1, name)


def list_agencies(
    conn: Connection, *, q: str | None = None, status: str | None = None, category: str | None = None
) -> list[dict]:
    """q: 기관명·약자 부분일치 검색. status/category: 정확히 일치하는 것만."""
    latest_run_sq = (
        select(source_run.c.source_id, func.max(source_run.c.id).label("latest_id"))
        .group_by(source_run.c.source_id)
        .subquery()
    )
    stmt = (
        select(
            org.c.id,
            org.c.name,
            org.c.abbr,
            org.c.category,
            org.c.notice_url,
            source.c.name.label("source_name"),
            source.c.org_name.label("channel_org_name"),
            source.c.homepage_url.label("source_homepage_url"),
            source.c.adapter_type,
            source.c.active.label("source_active"),
            source.c.legal_tier,
            source.c.legal_verified_at,
            source_run.c.status,
            source_run.c.run_at,
        )
        .select_from(org)
        .join(source, source.c.id == org.c.source_id, isouter=True)
        .join(latest_run_sq, latest_run_sq.c.source_id == source.c.id, isouter=True)
        .join(source_run, source_run.c.id == latest_run_sq.c.latest_id, isouter=True)
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(org.c.name.ilike(like), org.c.abbr.ilike(like)))
    if category:
        stmt = stmt.where(org.c.category == category)

    rows = conn.execute(stmt).mappings().all()

    now = datetime.now(timezone.utc)
    result = []
    for row in rows:
        if row["source_name"] is None:
            row_status = "no_source"  # 아직 어느 채널로 수집할지 정해지지 않음
        else:
            row_status = row["status"] if row["source_active"] else "inactive"
            if row_status is None:
                row_status = "no_run_yet"  # 채널은 있으나 아직 한 번도 수집 안 됨
        if status and row_status != status:
            continue
        verified_at = row["legal_verified_at"]
        # 채널이 아예 없는 발주기관(no_source)은 준법 확인 대상 자체가 아니다 — 경고 배지도 없음.
        compliance_overdue = row["source_name"] is not None and (
            verified_at is None or (now - verified_at) > timedelta(days=COMPLIANCE_WARNING_DAYS)
        )
        result.append(
            {
                "id": row["id"],
                "name": row["name"],
                "abbr": row["abbr"],
                "category": row["category"],
                "notice_url": row["notice_url"] or row["source_homepage_url"],
                "channel": row["channel_org_name"] or row["source_name"],
                "adapter_label": ADAPTER_LABELS.get(row["adapter_type"], row["adapter_type"]) if row["adapter_type"] else None,
                "status": row_status,
                "last_run_at": row["run_at"].isoformat() if row["run_at"] else None,
                # 준법 확인 배지(advisory INBOX #6) — 채널(source) 단위 값을 그대로 보여준다.
                "legal_tier": row["legal_tier"],
                "legal_verified_at": verified_at.isoformat() if verified_at else None,
                "compliance_overdue": compliance_overdue,
            }
        )
    result.sort(key=lambda r: _sort_key(r["name"]))
    return result
