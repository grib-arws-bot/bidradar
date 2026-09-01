"""advisory INBOX #8(2026-09-01, "Jeffrey 확정") 완료조건: 담당자 개인정보(이름·연락처·
이메일)는 매핑 단계·raw_payload 저장 단계 양쪽에서 코드가 막는다 — 우연히 스키마에 컬럼이
없어서가 아니라, 명시적으로 거부돼야 한다."""

from __future__ import annotations

import pytest

from app.collector.mapper import PII_BANNED_TARGET_FIELDS, TIER_B_BANNED_TARGET_FIELDS, validate_field_maps
from app.collector.pii import mask_pii


def test_mask_pii_redacts_known_official_contact_fields():
    item = {
        "ancmTl": "2026년도 연구개발 사업 공고",
        "sorgnNm": "한국연구재단",
        "managerName": "홍길동",
        "managerTel": "02-1234-5678",
        "ntceInsttOfclEmailAdrs": "hong@example.go.kr",
    }
    masked = mask_pii(item)
    assert masked["ancmTl"] == item["ancmTl"]
    assert masked["sorgnNm"] == item["sorgnNm"]  # 발주기관명(조직)은 개인정보가 아니라 안 건드림
    assert masked["managerName"] != "홍길동"
    assert masked["managerTel"] != "02-1234-5678"
    assert masked["ntceInsttOfclEmailAdrs"] != "hong@example.go.kr"


def test_mask_pii_recurses_into_nested_dicts_and_lists():
    payload = {"items": [{"managerName": "홍길동"}, {"managerName": "김철수"}]}
    masked = mask_pii(payload)
    assert masked["items"][0]["managerName"] != "홍길동"
    assert masked["items"][1]["managerName"] != "김철수"


def test_mask_pii_leaves_org_name_like_keys_alone():
    # deptNm/orgNm처럼 패턴에 우연히 걸릴 수 있는 조직명 키는 예외 처리돼 있어야 함
    item = {"deptNm": "정보통신기획평가원"}
    assert mask_pii(item)["deptNm"] == "정보통신기획평가원"


def test_validate_field_maps_rejects_pii_target_field():
    field_maps = [
        {"target_field": "title", "source_path": "$.title", "format_hint": None},
        {"target_field": "manager_name", "source_path": "$.managerName", "format_hint": None},
    ]
    with pytest.raises(ValueError, match="개인정보"):
        validate_field_maps(field_maps)


def test_validate_field_maps_accepts_clean_field_maps():
    field_maps = [{"target_field": "title", "source_path": "$.title", "format_hint": None}]
    validate_field_maps(field_maps)  # 예외 없이 통과해야 함
    validate_field_maps(field_maps, legal_tier="B")


def test_validate_field_maps_rejects_full_text_target_for_tier_b():
    field_maps = [
        {"target_field": "title", "source_path": "$.title", "format_hint": None},
        {"target_field": "body", "source_path": "$.fullText", "format_hint": None},
    ]
    validate_field_maps(field_maps, legal_tier="A")  # A등급은 원문 허용 — 통과
    with pytest.raises(ValueError, match="원문 전문"):
        validate_field_maps(field_maps, legal_tier="B")


def test_banned_field_sets_are_disjoint_from_required_notice_columns():
    # REQUIRED_FIELDS(title/org_name/open_dt/url)를 실수로 금지 목록에 넣지 않았는지 확인
    from app.collector.mapper import REQUIRED_FIELDS

    assert not (PII_BANNED_TARGET_FIELDS & set(REQUIRED_FIELDS))
    assert not (TIER_B_BANNED_TARGET_FIELDS & set(REQUIRED_FIELDS))
