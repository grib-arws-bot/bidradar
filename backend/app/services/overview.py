"""관리자 홈 대시보드 — 3개 카드로 재구성(2026-09-12 사용자 지시, 2026-09-01/05 4카드 설계에서
변경):
1. 고객 현황 — 고객 수, 보고서 생성·발송 수(월간 추이)
2. 시스템 현황 — 서버 자원(system_resources.py), Claude API 사용량(llm_usage.py), 데이터
   수집채널 상태(수집 대상만 — schedule_times가 있는 소스)
3. 공고 데이터 — 소스별 수집/분석 현황(누적) + 최근 14일 일별 수집 추이(미분석/첨부분석완료/
   AI분석완료로 분류)

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


def _month_start_kst() -> datetime:
    """이번 달 1일 00:00(KST)을 UTC-aware datetime으로 — Claude API 사용량을 "이번 달"
    누적으로만 보여달라는 2026-09-12 사용자 지시. timestamptz 컬럼과 그대로 비교 가능."""
    now_kst = datetime.now(_KST)
    return datetime(now_kst.year, now_kst.month, 1, tzinfo=_KST)


def get_system_overview(conn: Connection) -> dict:
    """카드 2(시스템 현황) — 서버 자원·Claude API 사용량(이번 달 누적)·수집채널 상태(수집
    대상만)."""
    all_sources = list_sources(conn)
    scheduled = [s for s in all_sources if s["schedule_times"]]
    channels = [
        {"id": s["id"], "name": s["name"], "status": s["status"], "last_run_at": s["last_run_at"]}
        for s in scheduled
    ]
    resources = get_system_resources()
    # BidRadar 자체 디스크 사용량 — customer_document(소개서 파일)까지 별도 업로드 볼륨 없이
    # DB에 그대로 저장하므로(customers.py 설계, 2026-09-05) pg_database_size가 "DB+파일"을
    # 사실상 전부 포함한다. 도커 이미지·컨테이너 로그·infra/backup-db.sh 백업 파일은 호스트
    # 파일시스템에 있어 컨테이너 안에서 측정 불가 — 조용히 빠뜨리지 않고 캡션으로 밝혀둔다.
    if resources["available"]:
        db_size_bytes = conn.execute(select(func.pg_database_size(func.current_database()))).scalar_one()
        resources["disk"]["app_used_bytes"] = db_size_bytes
    return {
        "resources": resources,
        "llm_usage": get_llm_usage_summary(conn, _month_start_kst()),
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


NOTICE_DAILY_SERIES_DAYS = 14


def _notice_daily_series(conn: Connection, days: int) -> list[dict]:
    """최근 `days`일(KST, 오늘 포함)의 일별 수집 추이 — "누적 스냅샷 하나로는 매일매일의
    변화가 안 보인다"는 2026-09-12 사용자 지시로 "어제" 단일 스냅샷을 대체. 소스별로 나누면
    선이 너무 많아져 안 보이므로 전체 소스를 합산한 분석상태별(미분석/첨부분석완료/AI분석완료)
    3계열로만 집계한다. 수집이 없었던 날도 0으로 채워 날짜가 끊기지 않게 한다."""
    latest_analysis_sq = (
        select(analysis.c.notice_id, analysis.c.step, analysis.c.status)
        .distinct(analysis.c.notice_id)
        .order_by(analysis.c.notice_id, analysis.c.ver.desc())
        .subquery()
    )
    day_expr = func.date(func.timezone("Asia/Seoul", notice.c.created_at))
    start_date: date = (datetime.now(_KST) - timedelta(days=days - 1)).date()
    stmt = (
        select(
            day_expr.label("day"),
            func.count().label("total"),
            func.count().filter(latest_analysis_sq.c.step == "A2_structure", latest_analysis_sq.c.status == "done").label("ai_analyzed"),
            func.count().filter(latest_analysis_sq.c.step == "A1_extract", latest_analysis_sq.c.status == "done").label("extracted_only"),
        )
        .select_from(notice)
        .join(latest_analysis_sq, latest_analysis_sq.c.notice_id == notice.c.id, isouter=True)
        .where(day_expr >= start_date)
        .group_by(day_expr)
    )
    by_day = {r["day"]: r for r in conn.execute(stmt).mappings().all()}

    result = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        r = by_day.get(d)
        total = r["total"] if r else 0
        ai_analyzed = r["ai_analyzed"] if r else 0
        extracted_only = r["extracted_only"] if r else 0
        result.append(
            {
                "date": d.isoformat(),
                "total": total,
                "ai_analyzed": ai_analyzed,
                "extracted_only": extracted_only,
                "unanalyzed": total - ai_analyzed - extracted_only,
            }
        )
    return result


def get_notice_overview(conn: Connection) -> dict:
    """카드 3(공고 데이터) — 소스별 누적(현재 살아있는 것만 — 삭제된 건 notice 테이블에서
    이미 빠져 있으므로 별도 필터 불필요) + 최근 14일 일별 수집 추이(전체 소스 합산)."""
    all_sources = {s["id"]: s["name"] for s in list_sources(conn)}

    def _attach_names(rows: list[dict]) -> list[dict]:
        return [dict(r, source_name=all_sources.get(r["source_id"], f"소스 {r['source_id']}")) for r in rows]

    return {
        "cumulative": _attach_names(_notice_breakdown_by_source(conn)),
        "daily": _notice_daily_series(conn, NOTICE_DAILY_SERIES_DAYS),
    }
