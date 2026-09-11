"""app/services/org_classification.py 검증 — 발주기관 산업분야 분류(2026-09-11). 실제
org 테이블에서 뽑은 샘플명으로 확인한다(우선순위 규칙이 실제 데이터에서 뒤섞이지 않는지가
핵심 — 예: "대학교병원"은 교육이 아니라 보건의료로 가야 한다)."""

from __future__ import annotations

from app.services.org_classification import classify_org_category


def test_classifies_hospital_over_university_when_both_match():
    # "대학교"(교육)와 "병원"(보건의료) 둘 다 들어있지만 보건의료가 더 구체적 — 규칙 순서 확인.
    assert classify_org_category("전북대학교병원") == "보건의료"
    assert classify_org_category("인하대학교 의과대학 부속병원") == "보건의료"


def test_classifies_education_institutions():
    assert classify_org_category("경상북도교육청") == "교육"
    assert classify_org_category("경상북도교육청 경상북도경산교육지원청") == "교육"
    assert classify_org_category("계명대학교 산학협력단") == "교육"
    assert classify_org_category("동서울대학") == "교육"


def test_classifies_defense_and_public_safety():
    assert classify_org_category("해병 제9691부대") == "국방치안"
    assert classify_org_category("법무부 대구지방교정청 경북북부제1교도소") == "국방치안"
    assert classify_org_category("해양경찰청 동해지방해양경찰청 울진해양경찰서") == "국방치안"


def test_classifies_agriculture_and_forestry():
    assert classify_org_category("한국농어촌공사 경북지역본부 청송.영양지사") == "농림수산"
    assert classify_org_category("산림조합중앙회 광양시산림조합") == "농림수산"


def test_classifies_construction_transport():
    assert classify_org_category("한국공항공사") == "건설교통"
    assert classify_org_category("경상남도 서부도로관리사업소") == "건설교통"


def test_classifies_culture_sports_tourism():
    assert classify_org_category("영상물등급위원회") == "문화체육관광"
    assert classify_org_category("재단법인 경상남도 관광재단") == "문화체육관광"


def test_falls_back_to_general_local_government_by_last_token_suffix():
    # "도"·"시"·"군"·"구"로 끝나는 지자체명 — 더 구체적인 규칙에 안 걸릴 때만 여기로 떨어진다.
    assert classify_org_category("서울특별시 강남구") == "지방행정"  # "특별시"가 먼저 걸림
    assert classify_org_category("경상남도 창원시") == "지방행정"
    assert classify_org_category("충청남도 예산군") == "지방행정"
    assert classify_org_category("경기도 용인시 처인구") == "지방행정"


def test_does_not_misclassify_generic_substring_containing_admin_char():
    # "도"·"시" 등은 다른 단어에도 흔히 섞여 있다 — 마지막 토큰이 실제로 그 글자로 "끝날
    # 때만" 지방행정으로 분류해야 하고, 그 외엔 미분류(None)로 남아야 한다(억지 분류 금지).
    assert classify_org_category("한국지식재산연구원") == "산업통상과학기술"  # "연구원" 매칭
    assert classify_org_category("오렌지나무 주식회사") is None  # 어디에도 안 걸림 — 미분류 유지


def test_returns_none_when_no_rule_matches():
    assert classify_org_category("(주)강원랜드") is None
    assert classify_org_category("위드위 주식회사") is None
