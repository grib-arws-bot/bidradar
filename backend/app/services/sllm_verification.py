"""사내 sLLM(소형 언어모델, Qwen3-4B Q4_K_M) 응답 검증 유틸리티(2026-09-20, 의사결정_로그
175번).

sLLM은 Haiku와 달리 강제 함수호출(JSON 스키마 강제)이 없고, 온도 0으로 결정적으로 돌려도
원문에 없는 토큰이 인용문에 섞여 드는 현상이 실측으로 확인됐다("tqdm" 등, 숫자·퍼센트
표현 근처에서 C·A 양쪽 다 재현 — sLLM팀 자체 파일럿 결과). CLAUDE.md S8 원칙 2("근거를
못 대는 항목은 노출하지 않는다")를 sLLM 응답에도 지키려면, 응답이 스스로 주장하는 근거를
그대로 믿지 말고 원문에 실제로 있는지 여기서 직접 재검증한다 — sLLM팀이 이미 하고 있다는
"토큰 70% 이상 일치" 관대한 검증으로는 이 환각을 못 걸렀으므로, 정확 일치(공백 차이만
허용)로 더 엄격하게 본다.

청크 기반 추출(A v1, 2,500자 단위·200자 겹침)에서 겹침 구간에 걸친 요구사항이 여러 청크에서
중복 추출되는 문제도 여기서 같이 정리한다.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("bidradar.sllm_verification")


def _normalize_for_grounding(text: str) -> str:
    """공백(줄바꿈·여러 칸) 차이만 무시하고 비교하기 위한 정규화 — 단어 하나라도 다르면
    다른 문자열로 취급한다(관대한 부분일치는 쓰지 않음, 위 모듈 docstring 참고)."""
    return re.sub(r"\s+", "", text)


def is_grounded(citation: str, source_text: str) -> bool:
    """citation(sLLM이 근거로 든 인용문·조문 위치 문구)이 실제로 source_text 안에 있는지
    확인한다. 비어 있으면(근거 자체가 없으면) 무조건 탈락 — S8 원칙 2와 동일한 기준."""
    if not citation or not source_text:
        return False
    return _normalize_for_grounding(citation) in _normalize_for_grounding(source_text)


def filter_grounded_requirements(requirements: list[dict], source_text: str) -> tuple[list[dict], list[dict]]:
    """requirements 배열에서 cite가 실제로 source_text에 있는 항목만 통과시킨다.
    (통과, 탈락) 튜플로 반환 — 탈락 항목은 호출부가 로그로 남겨야 조용한 실패가 안 된다."""
    grounded: list[dict] = []
    rejected: list[dict] = []
    for item in requirements:
        if is_grounded(item.get("cite", ""), source_text):
            grounded.append(item)
        else:
            rejected.append(item)
    return grounded, rejected


def dedupe_requirements(requirements: list[dict]) -> list[dict]:
    """청크 겹침 구간 때문에 같은 요구사항이 여러 청크에서 중복 추출되는 문제(2026-09-20,
    sLLM A(v1) 파일럿에서 실측 — 3,336자·3청크 테스트에서 재현) — req_text가 공백 무시하고
    완전히 같으면 첫 번째만 남긴다. 표현이 살짝만 다른 준중복까지는 잡지 않는다(다른 요구
    사항을 잘못 지우는 오탐이 더 위험하다고 판단)."""
    seen: set[str] = set()
    result: list[dict] = []
    for item in requirements:
        key = _normalize_for_grounding(item.get("req_text", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def sanitize_sllm_requirements(requirements: list[dict], source_text: str) -> dict:
    """sLLM(A v1)이 반환한 requirements 배열을 그대로 쓰지 않고 (1) 근거가 원문에 실제로
    있는지 검증 → (2) 청크 겹침으로 인한 중복 제거 순으로 정리해 반환한다. 몇 건이
    걸러졌는지도 함께 반환해 호출부가 로그를 남길 수 있게 한다(조용한 실패 금지)."""
    grounded, rejected = filter_grounded_requirements(requirements, source_text)
    deduped = dedupe_requirements(grounded)
    rejected_count = len(rejected)
    duplicate_count = len(grounded) - len(deduped)
    if rejected_count:
        logger.warning("sLLM 요구사항 %d건이 근거 검증 실패로 제외됨", rejected_count)
    if duplicate_count:
        logger.info("sLLM 요구사항 %d건이 청크 중복으로 제거됨", duplicate_count)
    return {
        "requirements": deduped,
        "rejected_ungrounded_count": rejected_count,
        "duplicate_count": duplicate_count,
    }
