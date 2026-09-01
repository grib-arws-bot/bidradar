"""소스 목록 — 관리자 페이지 "소스 관리"용 읽기 전용 조회(2026-09-01 요청).

전체 CRUD(등록·probe·suggest-map·dryrun·rollback, 구현스펙 03절 `/api/admin/sources`)는
아직 없음 — 지금은 현재 연동된 소스를 기관별로 한눈에 보는 목록만 제공한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from app.models import source, source_run

ADAPTER_LABELS = {"openapi": "오픈API", "feed": "피드", "html": "HTML 크롤링"}
# 마지막 준법 확인일로부터 이만큼 지나면 S5 화면에 경고 배지(advisory INBOX #6, 분기 재확인 주기)
COMPLIANCE_WARNING_DAYS = 90


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
            source.c.homepage_url,
            source.c.adapter_type,
            source.c.stage,
            source.c.active,
            source.c.legal_tier,
            source.c.legal_verified_at,
            source_run.c.status,
            source_run.c.run_at,
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
            }
        )
    return result
