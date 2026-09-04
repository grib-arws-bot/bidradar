"""S8 A2 — 요구사양 구조화(LLM). CLAUDE.md 타협 불가 원칙 1번:

"LLM은 규격서에서 요구사양을 추출·정규화만 한다. 충족 여부는 match.py가 규칙으로
판정한다." 이 모듈은 절대 judgement/matched_product_id를 채우지 않는다 — LLM 응답에
그런 필드가 섞여 와도 무시하고 항상 analysis_requirement 테이블 기본값(unknown/NULL)
그대로 둔다. 판정은 이후 A3(match.py)의 몫이다.

원칙 2("판정은 권고, 근거 없는 판정은 화면에 안 낸다")에 따라 cite(조문 위치)가 없는
항목은 저장하지 않는다. 원칙 3("자동 실행 금지")은 이 함수를 호출하는 쪽(관리자 명시적
버튼 클릭 또는 CLI)의 책임 — 이 모듈 자체는 auto_extract 같은 자동 트리거에 절대
연결하지 않는다(비용 발생, 구현스펙 07절 "비용 때문에 자주 호출하지 말 것").
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from app.config import settings
from app.models import analysis, analysis_doc, analysis_requirement
from app.security.url_guard import fetch

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# 100만 토큰당 USD — Anthropic 공식 가격표 기준 근사치(2026-09 확인). 요금이 바뀌면
# platform.claude.com 가격 페이지와 대조해 갱신할 것 — analysis.llm_cost는 정산용이 아니라
# 예산 감시용 근사값이다.
PRICING_PER_MTOK = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-opus-5": {"input": 15.00, "output": 75.00},
}

OPS = ("gte", "lte", "eq", "contains", "manual")

_MAX_DOC_CHARS = 120_000  # Haiku 컨텍스트(200k 토큰) 안에 여유 있게 들어오는 상한 — 넘으면 잘라내고 표시한다.

_TOOL_NAME = "extract_requirements"
_SYSTEM_PROMPT = """당신은 공공입찰 규격서에서 참여기업이 충족해야 할 요구사양을 추출하는 보조 도구입니다.

규칙:
1. 문서에 실제로 명시된 요구사항만 추출합니다 — 추측하거나 일반적인 상식으로 채우지 마세요.
2. 각 항목은 반드시 원문 조문 위치(cite)를 함께 답니다 — 장/절/항 번호나 표 제목처럼 문서에서
   다시 찾을 수 있는 표현으로 적으세요. 위치를 특정할 수 없으면 그 항목은 아예 추출하지 마세요.
3. 수치 비교 가능한 항목(예: "3년 이상 유지보수 실적")은 op을 gte/lte/eq 중 하나로, req_value에
   숫자만, req_unit에 단위를 분리해서 넣으세요.
4. 특정 목록에 포함되는지 여부(예: 보유해야 할 인증 목록)는 op="contains"로 넣으세요.
5. 서술형이라 규칙으로 판정할 수 없는 항목(예: "제안서에 구축 방안을 상세히 기술할 것")은
   op="manual"로 넣고 req_value/req_unit은 비워두세요.
6. 충족 여부를 판단하지 마세요 — 당신의 역할은 추출뿐입니다. judgement 같은 필드는 절대
   포함하지 마세요.
7. category는 "성능"/"인증"/"실적"/"인력"/"기타" 중 문서 맥락에 맞는 것으로 분류하세요."""

_REQUIREMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "req_text": {"type": "string", "description": "요구사항 원문을 간결하게 정리한 문장"},
                    "req_value": {"type": "string", "description": "비교 가능한 값(없으면 빈 문자열)"},
                    "req_unit": {"type": "string", "description": "단위(없으면 빈 문자열)"},
                    "op": {"type": "string", "enum": list(OPS)},
                    "cite": {"type": "string", "description": "문서 내 조문 위치"},
                },
                "required": ["category", "req_text", "op", "cite"],
            },
        }
    },
    "required": ["requirements"],
}


class LLMNotConfiguredError(Exception):
    """ANTHROPIC_API_KEY가 설정되지 않음 — 조용히 건너뛰지 않고 명시적으로 거부한다."""


class StructuringInProgressError(Exception):
    """이 analysis는 이미 A2 구조화가 완료됨 — 중복 LLM 호출(비용) 방지."""


def _collect_source_text(conn: Connection, analysis_id: int) -> str:
    docs = conn.execute(
        select(analysis_doc.c.name, analysis_doc.c.text)
        .where(analysis_doc.c.analysis_id == analysis_id, analysis_doc.c.extract_ok.is_(True))
        .order_by(analysis_doc.c.id)
    ).all()
    parts = [f"=== {name} ===\n{text}" for name, text in docs if text]
    combined = "\n\n".join(parts)
    if len(combined) > _MAX_DOC_CHARS:
        combined = combined[:_MAX_DOC_CHARS] + "\n\n[문서가 길어 이후 내용은 잘렸습니다]"
    return combined


def _call_anthropic(model: str, document_text: str) -> tuple[list[dict], int, int]:
    """(requirements, input_tokens, output_tokens)를 반환한다. HTTP 호출 자체가 실패하면
    그대로 예외를 던진다 — 실패해도 흔적 없이 사라지면 안 되므로 호출부가 analysis.status를
    반드시 갱신해야 한다."""
    payload = {
        "model": model,
        "max_tokens": 8000,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": f"다음은 공공입찰 규격서 원문입니다.\n\n{document_text}"}],
        "tools": [
            {
                "name": _TOOL_NAME,
                "description": "규격서에서 추출한 요구사양 목록을 구조화된 형태로 반환합니다.",
                "input_schema": _REQUIREMENT_SCHEMA,
            }
        ],
        "tool_choice": {"type": "tool", "name": _TOOL_NAME},
    }
    response = fetch(
        ANTHROPIC_MESSAGES_URL,
        method="POST",
        timeout=180,
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    body = response.json()
    if "error" in body:
        raise RuntimeError(f"Anthropic API 오류: {body['error'].get('message', body['error'])}")

    usage = body.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    tool_use = next((block for block in body.get("content", []) if block.get("type") == "tool_use"), None)
    if tool_use is None:
        raise RuntimeError("모델이 구조화된 형식으로 응답하지 않았습니다(tool_use 블록 없음)")

    requirements = tool_use.get("input", {}).get("requirements", [])
    return requirements, input_tokens, output_tokens


def _valid_items(raw_items: list[dict]) -> tuple[list[dict], int]:
    """cite 없는 항목은 근거 없는 추출이라 버린다(원칙 2). (유효 항목, 버린 개수)."""
    valid, skipped = [], 0
    for item in raw_items:
        category = (item.get("category") or "").strip()
        req_text = (item.get("req_text") or "").strip()
        op = item.get("op")
        cite = (item.get("cite") or "").strip()
        if not (category and req_text and cite and op in OPS):
            skipped += 1
            continue
        valid.append(
            {
                "category": category,
                "req_text": req_text,
                "req_value": (item.get("req_value") or "").strip() or None,
                "req_unit": (item.get("req_unit") or "").strip() or None,
                "op": op,
                "cite": cite,
            }
        )
    return valid, skipped


def run_structuring(conn: Connection, analysis_id: int, *, model: str = "claude-haiku-4-5-20251001") -> dict:
    """A2 — analysis_doc에 이미 추출된 텍스트(A1 결과)를 LLM으로 구조화해 analysis_requirement에
    쌓는다. 반환값은 요약(로그·테스트 검증용)."""
    if not settings.anthropic_api_key:
        raise LLMNotConfiguredError("ANTHROPIC_API_KEY가 설정되지 않았습니다 — infra/.env에 추가한 뒤 재기동하세요.")
    if model not in PRICING_PER_MTOK:
        raise ValueError(f"허용되지 않은 모델: {model} (허용: {', '.join(PRICING_PER_MTOK)})")

    row = conn.execute(select(analysis.c.notice_id).where(analysis.c.id == analysis_id)).first()
    if row is None:
        raise ValueError(f"분석을 찾을 수 없습니다: {analysis_id}")

    already = conn.execute(
        select(analysis_requirement.c.id).where(analysis_requirement.c.analysis_id == analysis_id).limit(1)
    ).first()
    if already:
        raise StructuringInProgressError(f"analysis id={analysis_id}는 이미 A2 구조화가 완료됐습니다 — 재실행하려면 새로 분석하세요.")

    document_text = _collect_source_text(conn, analysis_id)
    if not document_text:
        raise ValueError("추출된 문서 텍스트가 없어 구조화를 진행할 수 없습니다(A1이 먼저 성공해야 함).")

    conn.execute(
        analysis.update().where(analysis.c.id == analysis_id).values(status="running", step="A2_structure")
    )

    try:
        raw_items, input_tokens, output_tokens = _call_anthropic(model, document_text)
    except Exception as exc:  # noqa: BLE001 — 실패도 반드시 기록(CLAUDE.md "조용한 실패 금지")
        conn.execute(
            analysis.update()
            .where(analysis.c.id == analysis_id)
            .values(status="failed", step="A2_structure", finished_at=datetime.now(timezone.utc), verdict=str(exc))
        )
        raise

    cost = (input_tokens / 1_000_000) * PRICING_PER_MTOK[model]["input"] + (
        output_tokens / 1_000_000
    ) * PRICING_PER_MTOK[model]["output"]

    valid_items, skipped = _valid_items(raw_items)
    for item in valid_items:
        conn.execute(insert(analysis_requirement).values(analysis_id=analysis_id, **item))

    conn.execute(
        analysis.update()
        .where(analysis.c.id == analysis_id)
        .values(
            status="done",
            step="A2_structure",
            finished_at=datetime.now(timezone.utc),
            llm_tokens=analysis.c.llm_tokens + input_tokens + output_tokens,
            llm_cost=analysis.c.llm_cost + cost,
        )
    )

    return {
        "analysis_id": analysis_id,
        "extracted": len(raw_items),
        "saved": len(valid_items),
        "skipped_no_cite": skipped,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 4),
    }
