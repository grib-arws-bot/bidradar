"""수집 원문에서 담당자 개인정보(이름·연락처·이메일)를 제거한다(advisory INBOX #8,
"Jeffrey 확정" 2026-09-01). notice 테이블엔 애초에 담당자 개인정보 컬럼이 없어 매핑 단계는
구조적으로 안전하지만, raw_payload는 "원본 보존"이 원칙이라 이 경우엔 예외로 마스킹한다.

발주기관명(deptName 등 조직 단위 정보)은 개인정보가 아니므로 대상에서 뺀다 — 이름·연락처·
이메일만 마스킹 대상(INBOX #8 범위).
"""

from __future__ import annotations

import re

# 정부 오픈API에서 담당자(개인) 필드에 흔히 쓰이는 키 이름 패턴 — 대소문자 무시.
# "ofcl"은 나라장터 계열의 ntceInsttOfclNm/OfclTelNo/OfclEmailAdrs를, "manager"는
# 과기정통부 API의 managerName/managerTel을(INBOX #2 원문) 접미사 상관없이 잡는다.
_PII_KEY_PATTERN = re.compile(
    r"(ofcl|manager|charger|picnm|pic_?tel|담당자|연락처|휴대폰|이메일|e-?mail)",
    re.IGNORECASE,
)
# 패턴에 우연히 걸리지만 개인정보가 아닌 키(발주기관명 등)는 여기서 빼준다.
_PII_KEY_ALLOWLIST = {"deptnm", "deptname", "orgnm", "orgname", "sorgnnm", "ntceinsttnm"}

MASKED_VALUE = "[개인정보 마스킹됨]"


def _is_pii_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _PII_KEY_ALLOWLIST:
        return False
    return bool(_PII_KEY_PATTERN.search(key))


def mask_pii(value):
    """dict/list를 재귀적으로 훑어 담당자 개인정보로 보이는 키의 값을 마스킹한다.
    raw_payload 저장 직전, 그리고 map_item에 넘기기 전(이중 방어) 양쪽에서 호출한다.
    """
    if isinstance(value, dict):
        return {key: (MASKED_VALUE if _is_pii_key(key) else mask_pii(val)) for key, val in value.items()}
    if isinstance(value, list):
        return [mask_pii(item) for item in value]
    return value
