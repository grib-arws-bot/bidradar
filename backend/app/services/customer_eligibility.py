"""고객 자격 프로필(입찰 자격요건 검증, 2026-09-23) — `customer_interest.py`와 같은 전체
치환 패턴. 고객마다 자사 자격을 저장해 공고 쪽 구조화된 자격요건
(`app/models/analysis.py::analysis_eligibility`)과 규칙 비교(`app/services/analysis/
eligibility.py`)한다.

이 값은 추천 점수(`recommendation_signals.py`)에 절대 섞이지 않는다 — 별도 필터로만 쓴다
(사용자 지시, `eligibility.py` 모듈 docstring 참고).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.models import customer
from app.services.analysis.eligibility import COMPANY_SIZE_TIERS


@dataclass
class EligibilityDraft:
    company_size_tier: str | None = None
    has_research_institute: bool | None = None
    venture_cert: bool | None = None
    industry_codes: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)


def get_eligibility_profile(conn: Connection, customer_id: int) -> dict | None:
    row = conn.execute(
        select(
            customer.c.id,
            customer.c.name,
            customer.c.eligibility_company_size_tier,
            customer.c.eligibility_has_research_institute,
            customer.c.eligibility_venture_cert,
            customer.c.eligibility_industry_codes,
            customer.c.eligibility_certifications,
        ).where(customer.c.id == customer_id)
    ).mappings().first()
    if row is None:
        return None
    return {
        "customer_id": row["id"],
        "customer_name": row["name"],
        "company_size_tier": row["eligibility_company_size_tier"],
        "has_research_institute": row["eligibility_has_research_institute"],
        "venture_cert": row["eligibility_venture_cert"],
        "industry_codes": row["eligibility_industry_codes"] if isinstance(row["eligibility_industry_codes"], list) else [],
        "certifications": row["eligibility_certifications"] if isinstance(row["eligibility_certifications"], list) else [],
        "company_size_tiers": list(COMPANY_SIZE_TIERS),
    }


def save_eligibility_profile(conn: Connection, customer_id: int, draft: EligibilityDraft) -> None:
    """전체 치환 — customer_interest.save_interest_profile과 동일한 원칙."""
    if draft.company_size_tier is not None and draft.company_size_tier not in COMPANY_SIZE_TIERS:
        raise ValueError(f"허용되지 않은 기업규모: {draft.company_size_tier} (허용: {', '.join(COMPANY_SIZE_TIERS)})")

    conn.execute(
        customer.update().where(customer.c.id == customer_id).values(
            eligibility_company_size_tier=draft.company_size_tier,
            eligibility_has_research_institute=draft.has_research_institute,
            eligibility_venture_cert=draft.venture_cert,
            eligibility_industry_codes=[c.strip() for c in draft.industry_codes if c.strip()],
            eligibility_certifications=[c.strip() for c in draft.certifications if c.strip()],
        )
    )
