"""입찰 자격요건(회사 단위) 검증 — 규칙 비교 엔진. match.py(A3, 제품 스펙 대조)와 같은
철학을 쓰지만 비교 대상이 근본적으로 다르다(등급 집합·불리언 플래그·문자열 집합) — 별도
모듈로 둔다.

CLAUDE.md 타협 불가 원칙 1번과 같은 이유로 **단정할 수 없으면 항상 "unknown"(확인 필요)을
반환한다.** 한쪽이라도 값이 없으면(공고 쪽 추출 실패 또는 고객 프로필 미입력) 절대 ok/no로
추측하지 않는다.

이 모듈의 판정은 `recommendation_signals.py`의 점수(노이즈-OR 결합)에 절대 섞이지 않는다 —
별도 필터로만 쓴다(사용자 지시 — 자격 미달이어도 우회하는 사례가 있어 점수에 섞이면
잘못된 참여 판단으로 이어질 수 있음).
"""

from __future__ import annotations

from dataclasses import dataclass

Judgement = str  # "ok" | "no" | "unknown"

COMPANY_SIZE_TIERS = ("중소기업", "중견기업", "대기업")


@dataclass
class AxisVerdict:
    judgement: Judgement
    reason: str
    cite: str | None = None


def evaluate_company_size(allowed_tiers: list[str] | None, customer_tier: str | None, cite: str | None = None) -> AxisVerdict:
    if allowed_tiers is None:
        return AxisVerdict("unknown", "공고에서 기업규모 제한을 확인하지 못했습니다")
    if not allowed_tiers:
        return AxisVerdict("ok", "공고에 기업규모 제한이 없습니다")
    if customer_tier is None:
        return AxisVerdict("unknown", "자사 기업규모가 입력되지 않았습니다")
    matched = customer_tier in allowed_tiers
    return AxisVerdict(
        "ok" if matched else "no",
        f"허용 기업규모({', '.join(allowed_tiers)}) 중 자사({customer_tier}) {'포함' if matched else '미포함'}",
        cite,
    )


def evaluate_research_institute(
    required: bool | None, customer_has_institute: bool | None, cite: str | None = None
) -> AxisVerdict:
    if required is None:
        return AxisVerdict("unknown", "공고에서 연구소 보유 요건을 확인하지 못했습니다")
    if not required:
        return AxisVerdict("ok", "공고에 연구소 보유 요건이 없습니다")
    if customer_has_institute is None:
        return AxisVerdict("unknown", "자사 연구소 보유 여부가 입력되지 않았습니다")
    matched = customer_has_institute is True
    return AxisVerdict("ok" if matched else "no", f"연구소 보유 요건 있음 — 자사 {'보유' if matched else '미보유'}", cite)


def evaluate_venture_cert(
    required: bool | None, customer_has_cert: bool | None, cite: str | None = None
) -> AxisVerdict:
    if required is None:
        return AxisVerdict("unknown", "공고에서 벤처기업 인증 요건을 확인하지 못했습니다")
    if not required:
        return AxisVerdict("ok", "공고에 벤처기업 인증 요건이 없습니다")
    if customer_has_cert is None:
        return AxisVerdict("unknown", "자사 벤처기업 인증 여부가 입력되지 않았습니다")
    matched = customer_has_cert is True
    return AxisVerdict("ok" if matched else "no", f"벤처기업 인증 요건 있음 — 자사 {'보유' if matched else '미보유'}", cite)


def evaluate_industry_codes(
    required_codes: list[str] | None, customer_codes: list[str], cite: str | None = None
) -> AxisVerdict:
    if required_codes is None:
        return AxisVerdict("unknown", "공고에서 업종 제한을 확인하지 못했습니다")
    if not required_codes:
        return AxisVerdict("ok", "공고에 업종 제한이 없습니다")
    if not customer_codes:
        return AxisVerdict("unknown", "자사 업종코드가 입력되지 않았습니다")
    matched = bool(set(required_codes) & set(customer_codes))
    return AxisVerdict(
        "ok" if matched else "no",
        f"요구 업종({', '.join(required_codes)}) 중 자사 업종과 {'일치' if matched else '불일치'}",
        cite,
    )


def _normalize(text: str) -> str:
    return text.strip().casefold()


def evaluate_certifications(
    required_certs: list[str] | None, customer_certs: list[str], cite: str | None = None
) -> AxisVerdict:
    if required_certs is None:
        return AxisVerdict("unknown", "공고에서 요구 인증을 확인하지 못했습니다")
    if not required_certs:
        return AxisVerdict("ok", "공고에 요구 인증이 없습니다")
    if not customer_certs:
        return AxisVerdict("unknown", "자사 보유 인증이 입력되지 않았습니다")
    normalized_customer = {_normalize(c) for c in customer_certs}
    # match.py의 contains op과 같은 방식(부분 문자열 포함) — 요구 인증마다 자사 보유 인증
    # 목록 중 하나라도 부분 일치하면 보유로 본다.
    missing = [
        req for req in required_certs
        if not any(_normalize(req) in owned or owned in _normalize(req) for owned in normalized_customer)
    ]
    if missing:
        return AxisVerdict("no", f"미보유 인증: {', '.join(missing)}", cite)
    return AxisVerdict("ok", f"요구 인증({', '.join(required_certs)}) 전부 보유", cite)


def evaluate_eligibility(notice_axes: dict, customer_profile: dict) -> dict[str, AxisVerdict]:
    """notice_axes: analysis_eligibility 한 행을 dict화한 것. customer_profile: customer의
    자격 컬럼들을 dict화한 것. 5개 축 전부를 계산해 반환한다. cite는 제한이 실제로 있는
    축에서만 의미가 있다(제한 없음/확인불가인 축은 각 evaluate_* 함수가 cite를 무시함)."""
    return {
        "company_size": evaluate_company_size(
            notice_axes.get("company_size_allowed_tiers"), customer_profile.get("eligibility_company_size_tier"),
            notice_axes.get("company_size_cite"),
        ),
        "research_institute": evaluate_research_institute(
            notice_axes.get("research_institute_required"), customer_profile.get("eligibility_has_research_institute"),
            notice_axes.get("research_institute_cite"),
        ),
        "venture_cert": evaluate_venture_cert(
            notice_axes.get("venture_cert_required"), customer_profile.get("eligibility_venture_cert"),
            notice_axes.get("venture_cert_cite"),
        ),
        "industry_codes": evaluate_industry_codes(
            notice_axes.get("industry_codes_required"), customer_profile.get("eligibility_industry_codes") or [],
            notice_axes.get("industry_codes_cite"),
        ),
        "certifications": evaluate_certifications(
            notice_axes.get("certifications_required"), customer_profile.get("eligibility_certifications") or [],
            notice_axes.get("certifications_cite"),
        ),
    }


def overall_verdict(axes: dict[str, AxisVerdict]) -> Judgement:
    """하나라도 'no'면 'no'(가장 우선), 하나라도 'unknown'이면 'unknown', 전부 'ok'일 때만
    'ok' — 과대판정 방지(전부 확실히 충족돼야 "충족"으로 본다)."""
    judgements = {v.judgement for v in axes.values()}
    if "no" in judgements:
        return "no"
    if "unknown" in judgements:
        return "unknown"
    return "ok"
