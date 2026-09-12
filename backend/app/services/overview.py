"""관리자 홈 대시보드 — 3개 카드로 재구성(2026-09-12 사용자 지시, 2026-09-01/05 4카드 설계에서
변경):
1. 고객 현황 — 고객 수, 보고서 생성·발송 수(월간 추이)
2. 시스템 현황 — 서버 자원(system_resources.py), Claude API 사용량(llm_usage.py), 데이터
   수집채널 상태(수집 대상만 — schedule_times가 있는 소스)
3. 공고 데이터 — 소스별 수집/분석 현황(누적 + 어제, 미분석/첨부분석완료/AI분석완료로 분류)

별도 캐시 테이블 없이 조회 시점에 계산 — 이 정도 규모(공고 수만 건)에서는 무리 없다는
기존 판단(2026-09-01) 그대로 유지."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.engine import Connection

from app.models import analysis, customer, customer_interest, newsletter_report, notice, report_send_log
from app.services.llm_usage import get_llm_usage_summary
from app.services.source_registry import list_sources
from app.services.system_resources import get_system_resources

MONTHS_BACK = 6
_KST = timezone(timedelta(hours=9))


def _last_n_months(n: int) -> list[str]:
    """["2026-04", ..., "2026-09"] — 이번 달 포함 최근 n개월, 오래된 순."""
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month
    months = []
    for _ in range(n):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(months))


def _monthly_new_counts(conn: Connection, table, date_col, months: list[str]) -> dict[str, int]:
    earliest = datetime.strptime(months[0], "%Y-%m").replace(tzinfo=timezone.utc)
    month_expr = func.to_char(date_col, "YYYY-MM")
    rows = conn.execute(
        select(month_expr, func.count()).select_from(table).where(date_col >= earliest).group_by(month_expr)
    ).all()
    counts = dict.fromkeys(months, 0)
    for month, count in rows:
        if month in counts:
            counts[month] = count
    return counts


def get_customer_overview(conn: Connection) -> dict:
    """카드 1(고객 현황) — 고객 수·보고서 생성/발송 수의 최근 6개월 추이."""
    months = _last_n_months(MONTHS_BACK)
    window_start = datetime.strptime(months[0], "%Y-%m").replace(tzinfo=timezone.utc)

    total = conn.execute(select(func.count()).select_from(customer)).scalar_one()
    base_before_window = conn.execute(
        select(func.count()).select_from(customer).where(customer.c.created_at < window_start)
    ).scalar_one()

    new_customers = _monthly_new_counts(conn, customer, customer.c.created_at, months)
    reports_generated = _monthly_new_counts(conn, newsletter_report, newsletter_report.c.generated_at, months)
    reports_sent = _monthly_new_counts(conn, report_send_log, report_send_log.c.sent_at, months)

    running = base_before_window
    customer_totals = []
    for m in months:
        running += new_customers[m]
        customer_totals.append(running)

    with_interests = conn.execute(
        select(func.count(func.distinct(customer_interest.c.customer_id))).select_from(customer_interest)
    ).scalar_one()
    profile_summarized = conn.execute(
        select(func.count()).select_from(customer).where(customer.c.profile_summary_md.is_not(None))
    ).scalar_one()

    return {
        "total_customers": total,
        "with_interests": with_interests,
        "profile_summarized": profile_summarized,
        "monthly": {
            "months": months,
            "customer_total": customer_totals,
            "reports_generated": [reports_generated[m] for m in months],
            "reports_sent": [reports_sent[m] for m in months],
        },
        "recent_reports": _recent_reports(conn),
    }


def _recent_reports(conn: Connection, limit: int = 5) -> list[dict]:
    rows = conn.execute(
        select(
            newsletter_report.c.id, newsletter_report.c.token, newsletter_report.c.generated_at,
            newsletter_report.c.view_count, customer.c.name.label("customer_name"),
        )
        .select_from(newsletter_report)
        .join(customer, customer.c.id == newsletter_report.c.customer_id)
        .order_by(desc(newsletter_report.c.generated_at))
        .limit(limit)
    ).mappings().all()
    return [dict(r) | {"generated_at": r["generated_at"].isoformat()} for r in rows]


def get_system_overview(conn: Connection) -> dict:
    """카드 2(시스템 현황) — 서버 자원·Claude API 사용량·수집채널 상태(수집 대상만)."""
    all_sources = list_sources(conn)
    scheduled = [s for s in all_sources if s["schedule_times"]]
    channels = [
        {"id": s["id"], "name": s["name"], "status": s["status"], "last_run_at": s["last_run_at"]}
        for s in scheduled
    ]
    return {
        "resources": get_system_resources(),
        "llm_usage": get_llm_usage_summary(conn),
        "channels": channels,
    }


# 미분석/첨부분석완료/AI분석완료는 서로 배타적 — 실패 이력은 "아직 쓸모있게 분석되지
# 않음"으로 보아 미분석에 합친다(재시도로 회복 가능한 일시적 상태라 별도 라벨을 늘리지
# 않음, AnalysisTabsSection.tsx의 analysisDone/extractionDone 판정 기준과 동일).
def _notice_breakdown_by_source(conn: Connection, *, kst_date: "date | None" = None) -> list[dict]:
    latest_analysis_sq = (
        select(analysis.c.notice_id, analysis.c.step, analysis.c.status)
        .distinct(analysis.c.notice_id)
        .order_by(analysis.c.notice_id, analysis.c.ver.desc())
        .subquery()
    )
    stmt = (
        select(
            notice.c.source_id,
            func.count().label("total"),
            func.count().filter(latest_analysis_sq.c.step == "A2_structure", latest_analysis_sq.c.status == "done").label("ai_analyzed"),
            func.count().filter(latest_analysis_sq.c.step == "A1_extract", latest_analysis_sq.c.status == "done").label("extracted_only"),
        )
        .select_from(notice)
        .join(latest_analysis_sq, latest_analysis_sq.c.notice_id == notice.c.id, isouter=True)
        .group_by(notice.c.source_id)
    )
    if kst_date is not None:
        stmt = stmt.where(func.date(func.timezone("Asia/Seoul", notice.c.created_at)) == kst_date)
    rows = conn.execute(stmt).mappings().all()
    return [
        {
            "source_id": r["source_id"],
            "total": r["total"],
            "ai_analyzed": r["ai_analyzed"],
            "extracted_only": r["extracted_only"],
            "unanalyzed": r["total"] - r["ai_analyzed"] - r["extracted_only"],
        }
        for r in rows
    ]


def get_notice_overview(conn: Connection) -> dict:
    """카드 3(공고 데이터) — 소스별 누적(현재 살아있는 것만 — 삭제된 건 notice 테이블에서
    이미 빠져 있으므로 별도 필터 불필요) + 어제(KST 기준) 수집분 분석 현황."""
    all_sources = {s["id"]: s["name"] for s in list_sources(conn)}
    yesterday_kst: date = (datetime.now(_KST) - timedelta(days=1)).date()

    def _attach_names(rows: list[dict]) -> list[dict]:
        return [dict(r, source_name=all_sources.get(r["source_id"], f"소스 {r['source_id']}")) for r in rows]

    return {
        "cumulative": _attach_names(_notice_breakdown_by_source(conn)),
        "yesterday": _attach_names(_notice_breakdown_by_source(conn, kst_date=yesterday_kst)),
        "yesterday_date": yesterday_kst.isoformat(),
    }
