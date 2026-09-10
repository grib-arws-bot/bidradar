"""리포트 AI 코멘트(2026-09-05, "Phase 1" 보고서 최적화) — 공고 선별 자체는 여전히 규칙
기반(customer_interest.py top_matches, CLAUDE.md 원칙 1과 같은 이유로 LLM이 판정하지 않음).
이미 선별된 목록에 "왜 이 고객에게 의미있는지" 설명·전략 코멘트만 LLM(Sonnet)이 덧붙인다.
관리자가 수동으로 실행(자동 실행 금지).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from app.config import settings
from app.models import customer, newsletter_report
from app.security.url_guard import fetch

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# customer_profile.py와 동일 별칭·가격표(3곳뿐이라 공용 모듈로 뺄 정도는 아님).
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

_TOOL_NAME = "annotate_notices"
_SYSTEM_PROMPT = """당신은 영업 지원 도구입니다. 이미 규칙 기반으로 선별된 공공입찰·정부지원
공고 목록과 이 고객사의 프로필(소개서 요약)을 보고, 각 공고가 "왜 이 고객사에게 의미있는지"와
"참여를 고려한다면 어떤 전략적 포인트를 살펴야 하는지"를 짧게 설명하세요.

- 공고를 이 회사가 실제로 자격이 되는지, 충족 여부를 판정하지 마세요 — 그건 이 도구의 역할이
  아닙니다. 어디까지나 "왜 살펴볼 만한지"에 대한 설명입니다.
- 프로필과 공고 정보에 실제로 있는 내용에 근거하세요 — 회사가 가지고 있지 않은 역량이나
  실적을 지어내지 마세요. 근거가 약하면 "일반적인 관련성" 정도로 담백하게 쓰세요.
- commentary는 2~3문장, strategy는 1~2문장으로 짧게."""

_ANNOTATION_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "notice_id": {"type": "integer"},
                    "commentary": {"type": "string", "description": "왜 이 공고가 이 고객에게 의미있는지"},
                    "strategy": {"type": "string", "description": "참여 시 고려할 전략적 포인트"},
                },
                "required": ["notice_id", "commentary", "strategy"],
            },
        },
    },
    "required": ["items"],
}


class NoProfileError(Exception):
    """고객 프로필 요약이 아직 없음 — customer_profile.summarize_customer_profile을 먼저 실행해야 함."""


class LLMNotConfiguredError(Exception):
    pass


class ReportNotFoundError(Exception):
    pass


def _notice_brief(n: dict) -> dict:
    return {
        "notice_id": n["id"],
        "title": n["title"],
        "stage": n.get("stage"),
        "org_name": n.get("org_name"),
        "est_price": n.get("est_price"),
        "close_dt": n.get("close_dt"),
        "score": n.get("score"),
    }


def generate_report_commentary(conn: Connection, report_id: int, *, model: str = "claude-sonnet-5") -> dict:
    if not settings.anthropic_api_key:
        raise LLMNotConfiguredError("ANTHROPIC_API_KEY가 설정되지 않았습니다 — infra/.env에 추가한 뒤 재기동하세요.")
    if model not in PRICING_PER_MTOK:
        raise ValueError(f"허용되지 않은 모델: {model} (허용: {', '.join(PRICING_PER_MTOK)})")

    row = conn.execute(
        select(newsletter_report.c.customer_id, newsletter_report.c.notices).where(
            newsletter_report.c.id == report_id
        )
    ).first()
    if row is None:
        raise ReportNotFoundError(f"리포트를 찾을 수 없습니다: {report_id}")

    profile_md = conn.execute(
        select(customer.c.profile_summary_md).where(customer.c.id == row.customer_id)
    ).scalar_one_or_none()
    if not profile_md:
        raise NoProfileError("이 고객의 프로필 요약이 아직 없습니다 — 먼저 프로필 요약을 생성하세요.")

    notices = row.notices
    if not notices:
        return {"annotated": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    briefs = [_notice_brief(n) for n in notices]
    user_content = (
        f"[고객 프로필]\n{profile_md}\n\n[선별된 공고 목록(JSON)]\n{json.dumps(briefs, ensure_ascii=False)}"
    )
    payload = {
        "model": model,
        "max_tokens": 8000,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_content}],
        "tools": [
            {
                "name": _TOOL_NAME,
                "description": "각 공고에 대한 코멘트·전략을 구조화된 형태로 반환합니다.",
                "input_schema": _ANNOTATION_SCHEMA,
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
    tool_use = next((b for b in body.get("content", []) if b.get("type") == "tool_use"), None)
    if tool_use is None:
        raise RuntimeError("모델이 구조화된 형식으로 응답하지 않았습니다(tool_use 블록 없음)")

    annotations = {item["notice_id"]: item for item in tool_use.get("input", {}).get("items", [])}
    merged = []
    annotated = 0
    for n in notices:
        note = dict(n)
        annotation = annotations.get(n["id"])
        if annotation:
            note["ai_commentary"] = annotation.get("commentary")
            note["ai_strategy"] = annotation.get("strategy")
            annotated += 1
        merged.append(note)

    cost = (input_tokens / 1_000_000) * PRICING_PER_MTOK[model]["input"] + (
        output_tokens / 1_000_000
    ) * PRICING_PER_MTOK[model]["output"]

    conn.execute(
        update(newsletter_report)
        .where(newsletter_report.c.id == report_id)
        .values(
            notices=merged,
            ai_generated_at=datetime.now(timezone.utc),
            ai_tokens=newsletter_report.c.ai_tokens + input_tokens + output_tokens,
            ai_cost_usd=newsletter_report.c.ai_cost_usd + cost,
        )
    )

    return {
        "annotated": annotated,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 4),
    }
