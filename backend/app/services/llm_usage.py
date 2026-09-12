"""Claude API 사용량 집계(2026-09-12, 전체 현황 "시스템 현황" 카드) — Anthropic Admin API를
쓰지 않는다(사용자 지시 "claude admin api 아님") — CLAUDE.md가 이미 요구하는 대로 호출마다
DB에 남겨둔 토큰·비용을 그대로 합산한다. LLM 호출은 S8 A2·A5·A6 세 곳뿐이라던 원문 설명은
S8 심층분석 범위 기준이고, 실제로는 아래 4개 지점에서 비용이 발생한다(전부 이미 각자
테이블에 토큰·비용을 기록해두고 있었음 — 새로 만들 것 없이 합산만 하면 됨):

- A2 구조화(요구사항 추출) — analysis.llm_tokens/llm_cost
- 고객 프로필 요약 — customer.profile_summary_tokens/cost(단, 호출별이 아니라 누적 값이라
  "총 몇 번" 대신 "요약을 완료한 고객 수"로 건수를 대신한다)
- 보고서 AI 코멘트 — newsletter_report.ai_tokens/ai_cost_usd
- 공고별 AI 사업 추진 전략 — notice_strategy(input_tokens+output_tokens)/cost_usd
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from app.models import analysis, customer, newsletter_report, notice_strategy


def get_llm_usage_summary(conn: Connection) -> dict:
    a2_row = conn.execute(
        select(func.count(), func.coalesce(func.sum(analysis.c.llm_tokens), 0), func.coalesce(func.sum(analysis.c.llm_cost), 0))
        .where(analysis.c.step == "A2_structure", analysis.c.llm_tokens > 0)
    ).first()
    a2 = {"calls": a2_row[0], "tokens": a2_row[1], "cost_usd": float(a2_row[2])}

    profile_row = conn.execute(
        select(
            func.count().filter(customer.c.profile_summarized_at.is_not(None)),
            func.coalesce(func.sum(customer.c.profile_summary_tokens), 0),
            func.coalesce(func.sum(customer.c.profile_summary_cost), 0),
        )
    ).first()
    profile = {"calls": profile_row[0], "tokens": profile_row[1], "cost_usd": float(profile_row[2])}

    commentary_row = conn.execute(
        select(
            func.count().filter(newsletter_report.c.ai_generated_at.is_not(None)),
            func.coalesce(func.sum(newsletter_report.c.ai_tokens), 0),
            func.coalesce(func.sum(newsletter_report.c.ai_cost_usd), 0),
        )
    ).first()
    commentary = {"calls": commentary_row[0], "tokens": commentary_row[1], "cost_usd": float(commentary_row[2])}

    strategy_row = conn.execute(
        select(
            func.count(),
            func.coalesce(func.sum(notice_strategy.c.input_tokens + notice_strategy.c.output_tokens), 0),
            func.coalesce(func.sum(notice_strategy.c.cost_usd), 0),
        )
        .where(notice_strategy.c.status == "done")
    ).first()
    strategy = {"calls": strategy_row[0], "tokens": strategy_row[1], "cost_usd": float(strategy_row[2])}

    breakdown = {
        "structure": a2,
        "customer_profile": profile,
        "report_commentary": commentary,
        "notice_strategy": strategy,
    }
    return {
        "total_calls": sum(b["calls"] for b in breakdown.values()),
        "total_tokens": sum(b["tokens"] for b in breakdown.values()),
        "total_cost_usd": round(sum(b["cost_usd"] for b in breakdown.values()), 4),
        "breakdown": breakdown,
    }
