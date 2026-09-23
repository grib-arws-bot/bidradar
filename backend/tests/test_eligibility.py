"""입찰 자격요건(회사 단위) 판정 규칙 엔진 검증 — test_match.py와 같은 기준("과대판정
0건")을 이 파일에도 그대로 적용한다."""

from __future__ import annotations

import pytest

from app.services.analysis.eligibility import (
    evaluate_certifications,
    evaluate_company_size,
    evaluate_eligibility,
    evaluate_industry_codes,
    evaluate_research_institute,
    evaluate_venture_cert,
    overall_verdict,
)


# ---- evaluate_company_size --------------------------------------------------------------


def test_company_size_ok_when_no_restriction():
    assert evaluate_company_size([], "중소기업").judgement == "ok"


def test_company_size_ok_when_customer_tier_in_allowed():
    assert evaluate_company_size(["중소기업", "중견기업"], "중소기업").judgement == "ok"


def test_company_size_no_when_customer_tier_not_in_allowed():
    assert evaluate_company_size(["대기업"], "중소기업").judgement == "no"


# ---- evaluate_research_institute / evaluate_venture_cert ---------------------------------


def test_research_institute_ok_when_not_required():
    assert evaluate_research_institute(False, None).judgement == "ok"


def test_research_institute_ok_when_required_and_customer_has_it():
    assert evaluate_research_institute(True, True).judgement == "ok"


def test_research_institute_no_when_required_and_customer_lacks_it():
    assert evaluate_research_institute(True, False).judgement == "no"


def test_venture_cert_ok_when_not_required():
    assert evaluate_venture_cert(False, None).judgement == "ok"


def test_venture_cert_no_when_required_and_customer_lacks_it():
    assert evaluate_venture_cert(True, False).judgement == "no"


# ---- evaluate_industry_codes --------------------------------------------------------------


def test_industry_codes_ok_when_no_restriction():
    assert evaluate_industry_codes([], []).judgement == "ok"


def test_industry_codes_ok_when_overlap_exists():
    assert evaluate_industry_codes(["62010", "62021"], ["62010"]).judgement == "ok"


def test_industry_codes_no_when_no_overlap():
    assert evaluate_industry_codes(["62010"], ["47190"]).judgement == "no"


# ---- evaluate_certifications ---------------------------------------------------------------


def test_certifications_ok_when_no_restriction():
    assert evaluate_certifications([], []).judgement == "ok"


def test_certifications_ok_when_all_owned():
    assert evaluate_certifications(["ISO 9001"], ["ISO 9001 품질경영시스템"]).judgement == "ok"


def test_certifications_no_when_missing():
    assert evaluate_certifications(["ISO 9001", "ISO 27001"], ["ISO 9001"]).judgement == "no"


# ---- 애매하면 항상 unknown(과대판정 0건) ----------------------------------------------------


@pytest.mark.parametrize(
    "fn,args",
    [
        (evaluate_company_size, (None, "중소기업")),  # 공고 쪽 추출 실패
        (evaluate_company_size, (["중소기업"], None)),  # 자사 미입력
        (evaluate_research_institute, (None, True)),
        (evaluate_research_institute, (True, None)),
        (evaluate_venture_cert, (None, True)),
        (evaluate_venture_cert, (True, None)),
        (evaluate_industry_codes, (None, ["62010"])),
        (evaluate_industry_codes, (["62010"], [])),
        (evaluate_certifications, (None, ["ISO 9001"])),
        (evaluate_certifications, (["ISO 9001"], [])),
    ],
)
def test_ambiguous_cases_never_return_ok_or_no(fn, args):
    """과대판정 0건 — 공고 쪽 추출 실패든 자사 프로필 미입력이든, 애매하면 전부 unknown이어야
    한다(ok/no로 단정하면 안 됨)."""
    assert fn(*args).judgement == "unknown"


# ---- overall_verdict -----------------------------------------------------------------------


def test_overall_verdict_all_ok():
    axes = evaluate_eligibility(
        notice_axes={
            "company_size_allowed_tiers": [], "research_institute_required": False,
            "venture_cert_required": False, "industry_codes_required": [], "certifications_required": [],
        },
        customer_profile={},
    )
    assert overall_verdict(axes) == "ok"


def test_overall_verdict_no_takes_priority_over_unknown():
    """하나는 명백히 미충족(no), 다른 하나는 확인불가(unknown)면 전체는 no여야 한다 —
    "일부 확인 필요"라고 얼버무려 미충족 사실을 가리면 안 됨."""
    axes = evaluate_eligibility(
        notice_axes={
            "company_size_allowed_tiers": ["대기업"], "research_institute_required": None,
            "venture_cert_required": False, "industry_codes_required": [], "certifications_required": [],
        },
        customer_profile={"eligibility_company_size_tier": "중소기업"},
    )
    assert overall_verdict(axes) == "no"


def test_overall_verdict_unknown_when_any_axis_unresolved_and_none_fail():
    axes = evaluate_eligibility(
        notice_axes={
            "company_size_allowed_tiers": [], "research_institute_required": None,
            "venture_cert_required": False, "industry_codes_required": [], "certifications_required": [],
        },
        customer_profile={},
    )
    assert overall_verdict(axes) == "unknown"
