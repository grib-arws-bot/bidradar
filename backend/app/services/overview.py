"""관리자 홈 대시보드 — "전체 시스템 운영을 위한 관리자 페이지"(2026-09-01 요청).

2026-09-05 재정리 — 4개 카드(공고 데이터/등록된 고객/보고서 생성 현황/시스템 현황)로 구성.
별도 캐시 테이블 없이 조회 시점에 계산 — 이 정도 규모(공고 수만 건)에서는 무리 없다
(설계안 03절과 같은 판단)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.engine import Connection

from app.models import customer, customer_interest, newsletter_report, notice
from app.services.notice_query import count_tabs
from app.services.pending_analysis import count_pending
from app.services.source_registry import list_sources


def _notice_stats(conn: Connection) -> dict:
    total = conn.execute(select(func.count()).select_from(notice)).scalar_one()
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    since_7d = datetime.now(timezone.utc) - timedelta(days=7)
    added_24h = conn.execute(select(func.count()).select_from(notice).where(notice.c.created_at >= since_24h)).scalar_one()
    added_7d = conn.execute(select(func.count()).select_from(notice).where(notice.c.created_at >= since_7d)).scalar_one()
    tab_counts = count_tabs(conn)  # 공고 탐색 탭과 동일한 bid_status 정의 재사용(일관성 보장)
    return {
        "total": total,
        "added_24h": added_24h,
        "added_7d": added_7d,
        "in_progress": tab_counts.get("in_progress", 0),
        "closed": tab_counts.get("closed", 0),
    }


def _customer_stats(conn: Connection) -> dict:
    total = conn.execute(select(func.count()).select_from(customer)).scalar_one()
    with_interests = conn.execute(
        select(func.count(func.distinct(customer_interest.c.customer_id))).select_from(customer_interest)
    ).scalar_one()
    profile_summarized = conn.execute(
        select(func.count()).select_from(customer).where(customer.c.profile_summary_md.is_not(None))
    ).scalar_one()
    by_tier = dict(
        conn.execute(select(customer.c.plan_tier, func.count()).group_by(customer.c.plan_tier)).all()
    )
    return {
        "total": total,
        "with_interests": with_interests,
        "profile_summarized": profile_summarized,
        "by_tier": by_tier,
    }


def _report_stats(conn: Connection) -> dict:
    total = conn.execute(select(func.count()).select_from(newsletter_report)).scalar_one()
    since_7d = datetime.now(timezone.utc) - timedelta(days=7)
    added_7d = conn.execute(
        select(func.count()).select_from(newsletter_report).where(newsletter_report.c.generated_at >= since_7d)
    ).scalar_one()
    with_ai_commentary = conn.execute(
        select(func.count()).select_from(newsletter_report).where(newsletter_report.c.ai_generated_at.is_not(None))
    ).scalar_one()
    total_views = conn.execute(select(func.coalesce(func.sum(newsletter_report.c.view_count), 0))).scalar_one()
    return {
        "total": total,
        "added_7d": added_7d,
        "with_ai_commentary": with_ai_commentary,
        "total_views": total_views,
    }


def _source_health(conn: Connection) -> dict:
    """소스별 가장 최근 source_run 상태를 센다(S5 상태 배지 4종과 같은 기준).

    전체 상세 목록은 source_registry.list_sources — 여기선 그걸 재사용해 카드용으로 축약한다.
    """
    all_sources = list_sources(conn)
    counts = {"ok": 0, "warn": 0, "fail": 0, "inactive": 0, "no_run_yet": 0}
    sources = []
    last_run_at = None
    for s in all_sources:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
        sources.append({"id": s["id"], "name": s["name"], "status": s["status"], "last_run_at": s["last_run_at"]})
        if s["last_run_at"] and (last_run_at is None or s["last_run_at"] > last_run_at):
            last_run_at = s["last_run_at"]
    return {
        "counts": counts,
        "sources": sources,
        "total": len(all_sources),
        "last_run_at": last_run_at,  # list_sources()가 이미 isoformat 문자열로 준다
    }


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
        "notices": _notice_stats(conn),
        "customers": _customer_stats(conn),
        "reports": _report_stats(conn),
        "sources": _source_health(conn),
        "pending_analysis": count_pending(conn),
        "recent_reports": _recent_reports(conn),
    }
