"""공고별 자격요건 판정 조회 + 목록 필터 접합점(2026-09-23) — `analysis/eligibility.py`의
순수 비교 로직을 실제 DB 데이터(공고의 `analysis_eligibility` 최신 행 + 고객의 자격
프로필)에 연결한다.

판정은 캐싱하지 않고 매 요청마다 계산한다 — LLM 호출이 없는 순수 규칙 비교라 비용이
사실상 0이고, 캐싱하면 "고객이 프로필을 고쳤는데 예전 판정이 그대로 보인다"는 새로운
버그 클래스가 생긴다.
"""

from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.engine import Connection

from app.models import analysis, analysis_eligibility, customer
from app.services.analysis.eligibility import Judgement, evaluate_eligibility, overall_verdict


def _latest_eligibility_axes(conn: Connection, notice_id: int) -> dict | None:
    """이 공고의 가장 최근 analysis에 연결된 analysis_eligibility 행. 없으면(A2 미완료 또는
    구버전 분석) None."""
    row = conn.execute(
        select(analysis_eligibility)
        .select_from(analysis_eligibility)
        .join(analysis, analysis.c.id == analysis_eligibility.c.analysis_id)
        .where(analysis.c.notice_id == notice_id)
        .order_by(analysis.c.ver.desc())
        .limit(1)
    ).mappings().first()
    return dict(row) if row is not None else None


def _customer_eligibility_profile(conn: Connection, customer_id: int) -> dict | None:
    row = conn.execute(
        select(
            customer.c.eligibility_company_size_tier,
            customer.c.eligibility_has_research_institute,
            customer.c.eligibility_venture_cert,
            customer.c.eligibility_industry_codes,
            customer.c.eligibility_certifications,
        ).where(customer.c.id == customer_id)
    ).mappings().first()
    return dict(row) if row is not None else None


def get_eligibility_verdict(conn: Connection, customer_id: int, notice_id: int) -> dict | None:
    """반환: {"overall": "ok"/"no"/"unknown", "axes": {축이름: {judgement, reason, cite}}}.
    공고에 자격요건 구조화 데이터가 없거나(A2 미완료) 고객이 없으면 None — "판정 불가"와
    "전부 확인 필요"는 다른 상태다(전자는 화면에 아예 안 보여줘야 함)."""
    notice_axes = _latest_eligibility_axes(conn, notice_id)
    if notice_axes is None:
        return None
    customer_profile = _customer_eligibility_profile(conn, customer_id)
    if customer_profile is None:
        return None
    axes = evaluate_eligibility(notice_axes, customer_profile)
    return {
        "overall": overall_verdict(axes),
        "axes": {name: {"judgement": v.judgement, "reason": v.reason, "cite": v.cite} for name, v in axes.items()},
    }


def filter_notice_ids_by_eligibility(
    conn: Connection, notice_ids: list[int], customer_id: int, status: Judgement
) -> set[int]:
    """notice_ids 중 자격요건 종합 판정이 status와 일치하는 것만 남긴다. 배치 처리 —
    공고별로 반복 쿼리하지 않는다(a3_match_signal과 같은 "최신 ver" 배치 조회 패턴)."""
    if not notice_ids:
        return set()
    customer_profile = _customer_eligibility_profile(conn, customer_id)
    if customer_profile is None:
        return set()

    latest_ver = (
        select(analysis.c.notice_id, func.max(analysis.c.ver).label("max_ver"))
        .where(analysis.c.notice_id.in_(notice_ids))
        .group_by(analysis.c.notice_id)
        .subquery()
    )
    latest_analysis = (
        select(analysis.c.id, analysis.c.notice_id)
        .join(latest_ver, and_(analysis.c.notice_id == latest_ver.c.notice_id, analysis.c.ver == latest_ver.c.max_ver))
        .subquery()
    )
    rows = conn.execute(
        select(latest_analysis.c.notice_id, analysis_eligibility)
        .select_from(latest_analysis)
        .join(analysis_eligibility, analysis_eligibility.c.analysis_id == latest_analysis.c.id)
    ).mappings().all()

    matched: set[int] = set()
    for row in rows:
        axes = evaluate_eligibility(dict(row), customer_profile)
        if overall_verdict(axes) == status:
            matched.add(row["notice_id"])
    return matched
