"""관리자 홈 대시보드 — "전체 시스템 운영을 위한 관리자 페이지"(2026-09-01 요청).
소스 상태·수집 현황·공고 통계·고객 현황·최근 리포트를 한눈에 모은다. 별도 캐시 테이블 없이
조회 시점에 계산 — 이 정도 규모(공고 수만 건)에서는 무리 없다(설계안 03절과 같은 판단)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.engine import Connection

from app.models import customer, customer_interest, newsletter_report, notice, source, source_run


def _source_health(conn: Connection) -> dict:
    """소스별 가장 최근 source_run 상태를 센다(S5 상태 배지 4종과 같은 기준)."""
    latest_run_sq = (
        select(source_run.c.source_id, func.max(source_run.c.id).label("latest_id"))
        .group_by(source_run.c.source_id)
        .subquery()
    )
    rows = conn.execute(
        select(source.c.id, source.c.name, source.c.active, source_run.c.status, source_run.c.run_at)
        .select_from(source)
        .join(latest_run_sq, latest_run_sq.c.source_id == source.c.id, isouter=True)
        .join(source_run, source_run.c.id == latest_run_sq.c.latest_id, isouter=True)
    ).mappings().all()

    counts = {"ok": 0, "warn": 0, "fail": 0, "inactive": 0, "no_run_yet": 0}
    sources = []
    for row in rows:
        status = row["status"] if row["active"] else "inactive"
        if status is None:
            status = "no_run_yet"
        counts[status] = counts.get(status, 0) + 1
        sources.append(
            {"id": row["id"], "name": row["name"], "status": status, "last_run_at": row["run_at"].isoformat() if row["run_at"] else None}
        )
    return {"counts": counts, "sources": sources}


def _notice_stats(conn: Connection) -> dict:
    total = conn.execute(select(func.count()).select_from(notice)).scalar_one()
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    since_7d = datetime.now(timezone.utc) - timedelta(days=7)
    added_24h = conn.execute(select(func.count()).select_from(notice).where(notice.c.created_at >= since_24h)).scalar_one()
    added_7d = conn.execute(select(func.count()).select_from(notice).where(notice.c.created_at >= since_7d)).scalar_one()
    return {"total": total, "added_24h": added_24h, "added_7d": added_7d}


def _customer_stats(conn: Connection) -> dict:
    total = conn.execute(select(func.count()).select_from(customer)).scalar_one()
    with_interests = conn.execute(
        select(func.count(func.distinct(customer_interest.c.customer_id))).select_from(customer_interest)
    ).scalar_one()
    by_tier = dict(
        conn.execute(select(customer.c.plan_tier, func.count()).group_by(customer.c.plan_tier)).all()
    )
    return {"total": total, "with_interests": with_interests, "by_tier": by_tier}


def _recent_reports(conn: Connection, limit: int = 5) -> list[dict]:
    rows = conn.execute(
        select(
            newsletter_report.c.id,
            newsletter_report.c.token,
            newsletter_report.c.generated_at,
            newsletter_report.c.view_count,
            customer.c.name.label("customer_name"),
        )
        .select_from(newsletter_report)
        .join(customer, customer.c.id == newsletter_report.c.customer_id)
        .order_by(desc(newsletter_report.c.generated_at))
        .limit(limit)
    ).mappings().all()
    return [dict(r) | {"generated_at": r["generated_at"].isoformat()} for r in rows]


def get_overview(conn: Connection) -> dict:
    return {
        "sources": _source_health(conn),
        "notices": _notice_stats(conn),
        "customers": _customer_stats(conn),
        "recent_reports": _recent_reports(conn),
    }
