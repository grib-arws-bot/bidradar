"""관리자 홈 대시보드 — 3개 카드로 재구성(2026-09-12 사용자 지시, 2026-09-01/05 4카드 설계에서
변경):
1. 고객 현황(보고서 현황) — 고객 수, 보고서 생성·발송 수(월간 추이)
2. 시스템 현황 — 서버 자원(system_resources.py), Claude API 사용량(llm_usage.py), 데이터
   수집채널 상태(수집 대상만 — schedule_times가 있는 소스)
3. 공고 데이터 — 최근 14일 일별 추이 선 그래프 2개: 전체 소스 누적 총량 + 소스별 신규
   수집 건수(분석상태 구분 없음, 2026-09-12 — "값이 너무 차이나서 의미가 없다"는 피드백으로 뺌)

별도 캐시 테이블 없이 조회 시점에 계산 — 이 정도 규모(공고 수만 건)에서는 무리 없다는
기존 판단(2026-09-01) 그대로 유지."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.engine import Connection

from app.models import customer, customer_interest, newsletter_report, notice, report_send_log
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


NOTICE_DAILY_SERIES_DAYS = 14
NOTICE_TOTAL_SOURCE_ID = None  # "전체" 합산 계열의 source_id — 실제 소스 id와 안 겹치게 None


def _notice_daily_raw_data(conn: Connection, days: int):
    """두 그래프가 공통으로 쓰는 원자료 — (날짜 목록, 소스명 매핑, 소스별 window-이전 누적,
    소스별 일별 신규 건수). 분석상태별 구분(미분석/첨부분석완료/AI분석완료)은 2026-09-12
    사용자 지시로 뺐다 — "값이 너무 차이나서(대부분 미분석) 의미가 없다"는 실사용 피드백."""
    day_expr = func.date(func.timezone("Asia/Seoul", notice.c.created_at))
    start_date: date = (datetime.now(_KST) - timedelta(days=days - 1)).date()
    dates = [(start_date + timedelta(days=i)).isoformat() for i in range(days)]

    all_sources = {s["id"]: s["name"] for s in list_sources(conn)}
    source_ids = sorted(conn.execute(select(notice.c.source_id).distinct()).scalars().all())

    before_rows = conn.execute(
        select(notice.c.source_id, func.count().label("total"))
        .select_from(notice)
        .where(day_expr < start_date)
        .group_by(notice.c.source_id)
    ).mappings().all()
    before_by_source = {r["source_id"]: r["total"] for r in before_rows}

    daily_rows = conn.execute(
        select(day_expr.label("day"), notice.c.source_id, func.count().label("total"))
        .select_from(notice)
        .where(day_expr >= start_date)
        .group_by(day_expr, notice.c.source_id)
    ).mappings().all()
    daily_by_key = {(r["day"], r["source_id"]): r["total"] for r in daily_rows}

    return start_date, dates, all_sources, source_ids, before_by_source, daily_by_key


def get_notice_overview(conn: Connection) -> dict:
    """카드 3(공고 데이터) — 최근 14일(KST) 기준 선 그래프 2개, 각각 소스별 계열 + "전체"
    합산 계열(사용자 지시 "소스별과 전체소스를 그려줘"):
    1. 누적 데이터 — 그 날짜까지의 러닝토탈(삭제된 공고는 notice 테이블에서 이미 빠져
       있으므로 "삭제 데이터 제외"가 별도 필터 없이 자동으로 성립한다)
    2. 수집 데이터 — 그 날 신규로 수집된 건수"""
    days = NOTICE_DAILY_SERIES_DAYS
    start_date, dates, all_sources, source_ids, before_by_source, daily_by_key = _notice_daily_raw_data(conn, days)

    collected_series = []
    cumulative_series = []
    collected_grand_total = [0] * days
    for sid in source_ids:
        daily_counts = [daily_by_key.get((start_date + timedelta(days=i), sid), 0) for i in range(days)]
        collected_series.append(
            {"source_id": sid, "source_name": all_sources.get(sid, f"소스 {sid}"), "counts": daily_counts}
        )
        for i, c in enumerate(daily_counts):
            collected_grand_total[i] += c

        running = before_by_source.get(sid, 0)
        cumulative_counts = []
        for c in daily_counts:
            running += c
            cumulative_counts.append(running)
        cumulative_series.append(
            {"source_id": sid, "source_name": all_sources.get(sid, f"소스 {sid}"), "counts": cumulative_counts}
        )

    collected_series.append({"source_id": NOTICE_TOTAL_SOURCE_ID, "source_name": "전체", "counts": collected_grand_total})
    cumulative_grand_total = [sum(s["counts"][i] for s in cumulative_series) for i in range(days)]
    cumulative_series.append(
        {"source_id": NOTICE_TOTAL_SOURCE_ID, "source_name": "전체", "counts": cumulative_grand_total}
    )

    return {
        "cumulative_daily": {"dates": dates, "series": cumulative_series},
        "collected_daily": {"dates": dates, "series": collected_series},
    }
