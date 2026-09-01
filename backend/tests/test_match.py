"""S8 요구사양 판정 규칙 엔진 검증 — CLAUDE.md "test_match.py는 과대판정 0건을 보증한다"."""

from __future__ import annotations

import pytest

from app.services.analysis.match import evaluate_requirement


def test_gte_ok_and_no():
    assert evaluate_requirement("400", "gte", "500")[0] == "ok"
    assert evaluate_requirement("400", "gte", "300")[0] == "no"


def test_lte_ok_and_no():
    assert evaluate_requirement("10", "lte", "5")[0] == "ok"
    assert evaluate_requirement("10", "lte", "20")[0] == "no"


def test_eq_numeric_and_string():
    assert evaluate_requirement("4", "eq", "4.0")[0] == "ok"  # 숫자로 비교하면 4 == 4.0
    assert evaluate_requirement("IP66", "eq", "IP66")[0] == "ok"
    assert evaluate_requirement("IP66", "eq", "IP65")[0] == "no"


def test_contains_ok_and_no():
    assert evaluate_requirement("IP66", "contains", "방수등급 IP66 이상")[0] == "ok"
    assert evaluate_requirement("IP68", "contains", "방수등급 IP66 이상")[0] == "no"


def test_manual_is_always_unknown_even_when_values_would_match():
    judgement, note = evaluate_requirement("100", "manual", "100")
    assert judgement == "unknown"
    assert "사람" in note


def test_missing_product_value_is_unknown():
    assert evaluate_requirement("400", "gte", None)[0] == "unknown"


def test_unit_mismatch_is_unknown_even_when_numbers_would_match():
    # 400(만화소)와 400(만원)처럼 단위가 다르면 숫자가 같아도 절대 자동 판정하지 않는다
    judgement, note = evaluate_requirement("400", "gte", "500", req_unit="만화소", product_unit="만원")
    assert judgement == "unknown"
    assert "단위" in note


def test_non_numeric_value_on_numeric_op_is_unknown():
    assert evaluate_requirement("빠름", "gte", "매우 빠름")[0] == "unknown"


def test_unknown_op_is_unknown():
    assert evaluate_requirement("400", "between", "500")[0] == "unknown"


@pytest.mark.parametrize(
    "req_value,req_op,product_value,req_unit,product_unit",
    [
        ("400", "gte", None, None, None),  # 대조 대상 없음
        ("400", "manual", "999999", None, None),  # manual은 값이 뭐든 unknown
        ("400", "gte", "abc", None, None),  # 숫자 아님
        ("400", "gte", "500", "화소", "원"),  # 단위 불일치
        ("400", "weird_op", "500", None, None),  # 알 수 없는 op
    ],
)
def test_ambiguous_cases_never_return_ok_or_no(req_value, req_op, product_value, req_unit, product_unit):
    """과대판정 0건 — 애매한 입력은 전부 unknown이어야지, ok/no로 단정하면 안 된다."""
    judgement, _note = evaluate_requirement(
        req_value, req_op, product_value, req_unit=req_unit, product_unit=product_unit
    )
    assert judgement == "unknown"
