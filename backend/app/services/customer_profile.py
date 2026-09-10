"""고객 프로필 요약(2026-09-05, "Phase 1" 보고서 최적화 설계) — 고객이 올린 소개서
(customer_document)를 매 보고서 생성마다 LLM에 다시 넣는 대신, 한 번 요약해 MD로 캐싱해둔다
(사용자 확정 — 비용 절감·검증 가능성). 소개서를 새로 올리거나 바꿔도 자동 재요약하지 않는다
— 관리자가 버튼을 눌러야만 실행한다("고객사 AI 재분석은 관리자가 수동으로", CLAUDE.md
원칙 3 "자동 실행 금지"와 같은 이유).

기본 모델은 Sonnet — 이 요약이 이후 모든 보고서 코멘트 생성의 기반 자료가 되므로(1회성·저빈도
호출이라 비용 부담도 작음) Haiku보다 품질을 우선한다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from app.config import settings
from app.models import customer, customer_document
from app.security.url_guard import fetch
from app.services.document_extract import extract_document

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# structure.py와 같은 별칭·가격표(2곳뿐이라 공용 모듈로 뺄 정도는 아님) — 가격이 바뀌면 양쪽 다 갱신.
MODEL_ALIASES = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-5",
}
PRICING_PER_MTOK = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-opus-5": {"input": 15.00, "output": 75.00},
}

_MAX_DOC_CHARS = 60_000  # 소개서는 규격서(structure.py 120,000)보다 대체로 짧음

_SYSTEM_PROMPT = """당신은 영업 지원 도구입니다. 회사가 올린 소개서(회사소개서·제품소개서 등)
원문을 읽고, 이후 공공입찰·정부지원 공고 추천과 고객 전략 수립에 참고할 프로필을 한국어
마크다운으로 정리하세요.

**개조식으로 쓰세요** — "~다/~습니다"로 끝나는 완결된 문장이 아니라, "~함", "~보유", "~중심"
처럼 명사형·용언 어간으로 끝나는 짧은 불릿(`- `)으로 씁니다. 불릿 하나는 한 문장 분량을
넘기지 마세요.

다음 섹션을 포함하세요:
## 회사 개요
## 주요 제품/서비스
## 핵심 기술/차별화 포인트
## 주요 고객/실적
## 타겟 시장/분야

원문에 실제로 있는 내용만 쓰세요 — 지어내지 마세요. 섹션에 해당하는 원문 근거가 없으면
"- 정보 없음"이라고 쓰세요. 관리자가 이후 직접 다듬을 수 있으므로 과도하게 길게 쓰지 말고
핵심만 담으세요."""


class NoDocumentsError(Exception):
    """추출 가능한 소개서 파일이 없음 — 먼저 업로드해야 함."""


class LLMNotConfiguredError(Exception):
    pass


def _collect_document_text(conn: Connection, customer_id: int) -> str:
    rows = conn.execute(
        select(customer_document.c.filename, customer_document.c.content).where(
            customer_document.c.customer_id == customer_id
        )
    ).all()
    parts = []
    for filename, content in rows:
        result = extract_document(filename, content)
        if result.ok and result.text:
            parts.append(f"=== {filename} ===\n{result.text}")
    combined = "\n\n".join(parts)
    if len(combined) > _MAX_DOC_CHARS:
        combined = combined[:_MAX_DOC_CHARS] + "\n\n[문서가 길어 이후 내용은 잘렸습니다]"
    return combined


def summarize_customer_profile(conn: Connection, customer_id: int, *, model: str = "claude-sonnet-5") -> dict:
    """관리자가 명시적으로 호출할 때만 실행(자동 실행 금지) — 소개서 원문을 요약해
    customer.profile_summary_md에 저장한다. 반환값은 요약+비용(로그·화면 표시용)."""
    if not settings.anthropic_api_key:
        raise LLMNotConfiguredError("ANTHROPIC_API_KEY가 설정되지 않았습니다 — infra/.env에 추가한 뒤 재기동하세요.")
    if model not in PRICING_PER_MTOK:
        raise ValueError(f"허용되지 않은 모델: {model} (허용: {', '.join(PRICING_PER_MTOK)})")

    document_text = _collect_document_text(conn, customer_id)
    if not document_text:
        raise NoDocumentsError("추출 가능한 소개서 파일이 없습니다 — 먼저 파일을 업로드하세요.")

    payload = {
        "model": model,
        "max_tokens": 4000,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": f"다음은 회사 소개서 원문입니다.\n\n{document_text}"}],
    }
    response = fetch(
        ANTHROPIC_MESSAGES_URL,
        method="POST",
        timeout=120,
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
    text_block = next((b for b in body.get("content", []) if b.get("type") == "text"), None)
    if text_block is None:
        raise RuntimeError("모델이 텍스트로 응답하지 않았습니다.")
    summary_md = text_block["text"]

    cost = (input_tokens / 1_000_000) * PRICING_PER_MTOK[model]["input"] + (
        output_tokens / 1_000_000
    ) * PRICING_PER_MTOK[model]["output"]

    conn.execute(
        update(customer)
        .where(customer.c.id == customer_id)
        .values(
            profile_summary_md=summary_md,
            profile_summarized_at=datetime.now(timezone.utc),
            profile_summary_tokens=customer.c.profile_summary_tokens + input_tokens + output_tokens,
            profile_summary_cost=customer.c.profile_summary_cost + cost,
        )
    )

    return {
        "summary_md": summary_md,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 4),
    }


def save_manual_profile_summary(conn: Connection, customer_id: int, summary_md: str) -> None:
    """관리자가 AI 요약을 직접 손질할 때(개조식 다듬기·오탈자 수정 등) — LLM을 다시 부르지
    않고 텍스트만 갱신한다. profile_summarized_at("마지막 AI 생성 시각")은 건드리지 않는다 —
    수동 편집은 새로운 AI 생성이 아니므로."""
    conn.execute(update(customer).where(customer.c.id == customer_id).values(profile_summary_md=summary_md))
