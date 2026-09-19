"""app/services/sllm_verification.py 검증 — 사내 sLLM 응답의 근거 재검증·청크 중복 제거.

전부 순수 함수라 DB·네트워크 없이 검증한다.
"""

from __future__ import annotations

from app.services.sllm_verification import (
    dedupe_requirements,
    filter_grounded_requirements,
    is_grounded,
    sanitize_sllm_requirements,
)

SOURCE_TEXT = "제3조(자격요건) 참여기업은 최근 3년간 매출액 10억원 이상이어야 한다.\n제4조(제출서류) 사업자등록증 사본을 제출한다."


def test_is_grounded_true_for_exact_substring():
    assert is_grounded("최근 3년간 매출액 10억원 이상이어야 한다", SOURCE_TEXT) is True


def test_is_grounded_true_ignoring_whitespace_differences():
    # 줄바꿈·띄어쓰기만 다른 경우는 같은 문장으로 본다
    assert is_grounded("최근 3년간   매출액\n10억원 이상이어야 한다", SOURCE_TEXT) is True


def test_is_grounded_false_when_hallucinated_token_inserted():
    # 실측된 "tqdm" 환각 패턴 재현 — 원문에 없는 단어가 하나 끼어들면 탈락해야 한다
    assert is_grounded("최근 3년간 매출액 10억원 tqdm 이상이어야 한다", SOURCE_TEXT) is False


def test_is_grounded_false_for_empty_citation():
    assert is_grounded("", SOURCE_TEXT) is False


def test_filter_grounded_requirements_splits_pass_and_reject():
    requirements = [
        {"req_text": "매출액 요건", "cite": "최근 3년간 매출액 10억원 이상이어야 한다"},
        {"req_text": "환각 근거", "cite": "최근 3년간 매출액 tqdm 10억원 이상이어야 한다"},
        {"req_text": "근거 없음", "cite": ""},
    ]
    grounded, rejected = filter_grounded_requirements(requirements, SOURCE_TEXT)
    assert [r["req_text"] for r in grounded] == ["매출액 요건"]
    assert [r["req_text"] for r in rejected] == ["환각 근거", "근거 없음"]


def test_dedupe_requirements_removes_exact_duplicates_across_chunks():
    # 청크 겹침 구간(200자)에 걸친 동일 요구사항이 여러 청크에서 각각 추출되는 상황 재현
    requirements = [
        {"req_text": "매출액 10억원 이상", "cite": "..."},
        {"req_text": "제출서류 사본 제출", "cite": "..."},
        {"req_text": "매출액   10억원\n이상", "cite": "..."},  # 공백만 다른 동일 항목(겹침 구간)
    ]
    deduped = dedupe_requirements(requirements)
    assert len(deduped) == 2
    assert deduped[0]["req_text"] == "매출액 10억원 이상"  # 첫 번째가 유지됨


def test_sanitize_sllm_requirements_reports_counts():
    requirements = [
        {"req_text": "매출액 요건", "cite": "최근 3년간 매출액 10억원 이상이어야 한다"},
        {"req_text": "매출액 요건", "cite": "최근 3년간 매출액 10억원 이상이어야 한다"},  # 청크 중복
        {"req_text": "환각 근거", "cite": "매출액 10억원 tqdm 이상"},  # 근거 검증 실패
    ]
    result = sanitize_sllm_requirements(requirements, SOURCE_TEXT)
    assert [r["req_text"] for r in result["requirements"]] == ["매출액 요건"]
    assert result["rejected_ungrounded_count"] == 1
    assert result["duplicate_count"] == 1
