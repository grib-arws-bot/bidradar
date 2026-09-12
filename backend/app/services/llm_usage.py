"""Claude API 사용량 집계(2026-09-12, 전체 현황 "시스템 현황" 카드) — Anthropic Admin API를
쓰지 않는다(사용자 지시 "claude admin api 아님") — CLAUDE.md가 이미 요구하는 대로 호출마다
DB에 남겨둔 토큰·비용을 그대로 합산한다. LLM 호출은 S8 A2·A5·A6 세 곳뿐이라던 원문 설명은
S8 심층분석 범위 기준이고, 실제로는 아래 4개 지점에서 비용이 발생한다(전부 이미 각자
테이블에 토큰·비용을 기록해두고 있었음 — 새로 만들 것 없이 합산만 하면 됨):

- A2 구조화(요구사항 추출) — analysis.llm_tokens/llm_cost (시각: created_at)
- 고객 프로필 요약 — customer.profile_summary_tokens/cost (시각: profile_summarized_at)
- 보고서 AI 코멘트 — newsletter_report.ai_tokens/ai_cost_usd (시각: ai_generated_at)
- 공고별 AI 사업 추진 전략 — notice_strategy(input_tokens+output_tokens)/cost_usd (시각: updated_at)

**월별 집계(2026-09-12 사용자 지시 — "매월 1일부터 한달간 누적")** — `month_start` 이후 발생한
호출만 합산한다. 단 고객 프로필 요약은 근본적 한계가 있다: `profile_summary_tokens/cost`가
호출별 로그가 아니라 고객 행 하나에 계속 더해지는 누적 값이라(재요약할 때마다 `+=`), "이번 달에
실제로 쓴 토큰"을 정확히 분리할 방법이 없다 — 대신 `profile_summarized_at`(마지막 요약 시각)이
이번 달인 고객만 골라 그 고객의 누적값 전체를 이번 달 몫으로 잡는 근사치를 쓴다(재요약이 관리자
수동 버튼으로만 드물게 일어나 실제 오차는 작음, CLAUDE.md 조용한 실패 금지 원칙에 따라 이 근사가
있다는 사실 자체를 숨기지 않고 여기 남겨둔다). 정확히 하려면 호출별 로그 테이블이 새로 필요함.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from app.models import analysis, customer, newsletter_report, notice_strategy


def get_llm_usage_summary(conn: Connection, month_start: datetime) -> dict:
    a2_row = conn.execute(
        select(func.count(), func.coalesce(func.sum(analysis.c.llm_tokens), 0), func.coalesce(func.sum(analysis.c.llm_cost), 0))
        .where(analysis.c.step == "A2_structure", analysis.c.llm_tokens > 0, analysis.c.created_at >= month_start)
    ).first()
    a2 = {"calls": a2_row[0], "tokens": a2_row[1], "cost_usd": float(a2_row[2])}

    profile_row = conn.execute(
        select(
            func.count().filter(customer.c.profile_summarized_at.is_not(None)),
            func.coalesce(func.sum(customer.c.profile_summary_tokens), 0),
            func.coalesce(func.sum(customer.c.profile_summary_cost), 0),
        ).where(customer.c.profile_summarized_at >= month_start)
    ).first()
    profile = {"calls": profile_row[0], "tokens": profile_row[1], "cost_usd": float(profile_row[2])}

    commentary_row = conn.execute(
        select(
            func.count().filter(newsletter_report.c.ai_generated_at.is_not(None)),
            func.coalesce(func.sum(newsletter_report.c.ai_tokens), 0),
            func.coalesce(func.sum(newsletter_report.c.ai_cost_usd), 0),
        ).where(newsletter_report.c.ai_generated_at >= month_start)
    ).first()
    commentary = {"calls": commentary_row[0], "tokens": commentary_row[1], "cost_usd": float(commentary_row[2])}

    strategy_row = conn.execute(
        select(
            func.count(),
            func.coalesce(func.sum(notice_strategy.c.input_tokens + notice_strategy.c.output_tokens), 0),
            func.coalesce(func.sum(notice_strategy.c.cost_usd), 0),
        )
        .where(notice_strategy.c.status == "done", notice_strategy.c.updated_at >= month_start)
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
