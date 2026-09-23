"""A2 자격요건 구조화 확장(2026-09-23) — `structure.py`의 `summary.eligibility`는 지금까지
전부 자유서술 prose였다(company_size: "중소기업만 해당" 같은 문자열). 이 모듈은 그 옆에
tri-state 구조화 필드(`structured`)를 추가해 규칙 비교(`analysis/eligibility.py`)가 가능한
값으로 만든다.

`structure.py`가 이미 500줄 상한을 넘어 있어(2026-09-23 기준 554줄) 스키마·검증 로직을
여기로 분리했다 — `structure.py`는 이 모듈이 만든 조각을 가져다 붙이기만 한다.

검증 철학은 `_valid_items`(같은 파일의 요구사항 검증)와 동일 — cite 없는 "제한 있음" 주장은
근거 없는 판정이라 통째로 버린다(S8 원칙 2). "제한 없음"은 근거 인용이 필요한 적극적 판정이
아니므로 cite 없이도 그대로 받아들인다.
"""

from __future__ import annotations

from app.services.analysis.eligibility import COMPANY_SIZE_TIERS

_ELIGIBILITY_STRUCTURED_SCHEMA = {
    "type": "object",
    "properties": {
        "company_size": {
            "type": "object",
            "properties": {
                "restricted": {"type": "boolean", "description": "기업규모 제한이 있으면 true"},
                "allowed_tiers": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(COMPANY_SIZE_TIERS)},
                    "description": "restricted가 true일 때만 채움 — 허용되는 기업규모 목록",
                },
                "cite": {"type": "string", "description": "restricted가 true면 필수 — 문서 내 조문 위치"},
            },
            "required": ["restricted", "allowed_tiers", "cite"],
        },
        "research_institute": {
            "type": "object",
            "properties": {
                "required": {"type": "boolean", "description": "연구소(부설연구소 등) 보유 요건이 있으면 true"},
                "cite": {"type": "string"},
            },
            "required": ["required", "cite"],
        },
        "venture_cert": {
            "type": "object",
            "properties": {
                "required": {"type": "boolean", "description": "벤처기업 인증 요건이 있으면 true"},
                "cite": {"type": "string"},
            },
            "required": ["required", "cite"],
        },
        "industry_codes": {
            "type": "object",
            "properties": {
                "restricted": {"type": "boolean", "description": "업종(업종코드) 제한이 있으면 true"},
                "codes": {"type": "array", "items": {"type": "string"}, "description": "restricted가 true일 때만 채움"},
                "cite": {"type": "string"},
            },
            "required": ["restricted", "codes", "cite"],
        },
        "certifications": {
            "type": "object",
            "properties": {
                "restricted": {"type": "boolean", "description": "기타 보유 자격·인증 요건이 있으면 true"},
                "items": {"type": "array", "items": {"type": "string"}, "description": "restricted가 true일 때만 채움"},
                "cite": {"type": "string"},
            },
            "required": ["restricted", "items", "cite"],
        },
    },
    "required": ["company_size", "research_institute", "venture_cert", "industry_codes", "certifications"],
}

_ELIGIBILITY_PROMPT_NOTE = """- eligibility.structured: 위 eligibility 5개 항목을 규칙으로 비교할 수 있게 별도로도
  구조화하세요. 각 축마다 "제한이 있는지"부터 명시하고, **있으면 반드시 cite(문서 내 위치)를
  채우고, 문서에 그 축에 대한 언급 자체가 없으면 제한 없음(false)으로 두고 cite는 비워두세요.
  추측하지 마세요 — 문서에 없으면 없다고 답하세요.**
  - company_size: {restricted, allowed_tiers(제한 있을 때만 — "중소기업"/"중견기업"/"대기업" 중 허용되는 것들), cite}
  - research_institute: {required(연구소 보유 요건 여부), cite}
  - venture_cert: {required(벤처기업 인증 요건 여부), cite}
  - industry_codes: {restricted, codes(제한 있을 때만 — 업종코드 또는 업종명), cite}
  - certifications: {restricted, items(제한 있을 때만 — 요구 인증명), cite}"""


def _tri_state_axis(raw: dict, list_key: str, *, valid_values: tuple[str, ...] | None = None) -> tuple[list | None, str | None]:
    """restricted=true인데 cite가 없으면 통째로 버린다(값도 cite도 None — "확인 필요"로
    처리됨). restricted=false면 cite 없이도 빈 리스트로 받아들인다(문서에 없다는 건 근거
    인용이 필요한 적극적 판정이 아님). restricted 자체가 없으면(스키마 위반 등) None."""
    restricted = raw.get("restricted")
    cite = (raw.get("cite") or "").strip()
    if restricted is True:
        if not cite:
            return None, None
        values = [v for v in (raw.get(list_key) or []) if isinstance(v, str) and v.strip()]
        if valid_values is not None:
            values = [v for v in values if v in valid_values]
        return values, cite
    if restricted is False:
        return [], None
    return None, None


def _bool_axis(raw: dict) -> tuple[bool | None, str | None]:
    required = raw.get("required")
    cite = (raw.get("cite") or "").strip()
    if required is True:
        if not cite:
            return None, None
        return True, cite
    if required is False:
        return False, None
    return None, None


def valid_eligibility_axes(raw: dict | None) -> dict | None:
    """summary.eligibility.structured(LLM 원본)를 analysis_eligibility insert용 dict로
    변환한다. 5개 축 전부 확인불가(None)면 저장할 정보가 없다는 뜻이라 None을 반환해
    호출부가 행 자체를 안 만들게 한다."""
    if not isinstance(raw, dict):
        return None

    company_size_allowed_tiers, company_size_cite = _tri_state_axis(
        raw.get("company_size") or {}, "allowed_tiers", valid_values=COMPANY_SIZE_TIERS
    )
    research_institute_required, research_institute_cite = _bool_axis(raw.get("research_institute") or {})
    venture_cert_required, venture_cert_cite = _bool_axis(raw.get("venture_cert") or {})
    industry_codes_required, industry_codes_cite = _tri_state_axis(raw.get("industry_codes") or {}, "codes")
    certifications_required, certifications_cite = _tri_state_axis(raw.get("certifications") or {}, "items")

    result = {
        "company_size_allowed_tiers": company_size_allowed_tiers,
        "company_size_cite": company_size_cite,
        "research_institute_required": research_institute_required,
        "research_institute_cite": research_institute_cite,
        "venture_cert_required": venture_cert_required,
        "venture_cert_cite": venture_cert_cite,
        "industry_codes_required": industry_codes_required,
        "industry_codes_cite": industry_codes_cite,
        "certifications_required": certifications_required,
        "certifications_cite": certifications_cite,
    }
    if all(v is None for v in result.values()):
        return None
    return result
