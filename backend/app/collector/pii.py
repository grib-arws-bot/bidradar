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
# "refrnc"는 기업마당(bizinfo.go.kr) API의 refrncNm(문의처 담당자명)을 잡으려고 추가함
# (2026-09-02 기업마당 기술검토 중 발견 — 이 패턴 없이는 안 걸리는 실제 사례였음).
# "telno"/"celno"/"mbr"는 IRIS 사업진행안내·사업설명회(게시판형) 엔드포인트 조사 중 발견
# (2026-09-02) — telNo/celNo(전화·휴대폰)·wrtrMbrNm/wrtrMbrWholNm(작성자명)·frstRegMbrIdNm
# 등이 목록 응답에 그대로 노출됨. "mbr"는 광범위해 보이지만 이 도메인(정부 API 필드명)에서
# "회원(멤버) 관련 식별자"는 전부 개인 식별과 엮여 있어 통째로 막는 쪽이 안전(과다 마스킹이
# 과소 마스킹보다 싸다).
_PII_KEY_PATTERN = re.compile(
    r"(ofcl|manager|charger|picnm|pic_?tel|refrnc|telno|celno|mbr|담당자|연락처|휴대폰|이메일|e-?mail)",
    re.IGNORECASE,
)
# 패턴에 우연히 걸리지만 개인정보가 아닌 키(발주기관명 등)는 여기서 빼준다.
_PII_KEY_ALLOWLIST = {"deptnm", "deptname", "orgnm", "orgname", "sorgnnm", "ntceinsttnm"}

MASKED_VALUE = "[개인정보 마스킹됨]"


def is_pii_like_key(key: str) -> bool:
    """공개 함수 — app/collector/mapper.py가 "extra:" 필드 매핑을 검사할 때도 재사용한다
    (2026-09-02, notice.extra 도입)."""
    lowered = key.lower()
    if lowered in _PII_KEY_ALLOWLIST:
        return False
    return bool(_PII_KEY_PATTERN.search(key))


def mask_pii(value):
    """dict/list를 재귀적으로 훑어 담당자 개인정보로 보이는 키의 값을 마스킹한다.
    raw_payload 저장 직전, 그리고 map_item에 넘기기 전(이중 방어) 양쪽에서 호출한다.
    """
    if isinstance(value, dict):
        return {key: (MASKED_VALUE if is_pii_like_key(key) else mask_pii(val)) for key, val in value.items()}
    if isinstance(value, list):
        return [mask_pii(item) for item in value]
    return value
