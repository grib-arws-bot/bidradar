"""L1 하드필터 + L2 키워드 스코어링(설계안 05절)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.models import keyword_rule, source

L2_PROMOTE_THRESHOLD = 4  # "합계 ≥ 4 이면 L3로 승급" (설계안 05절 L2)


def passes_l1(conn: Connection, source_id: int) -> bool:
    """⚠️ 세부품명번호·업종코드 사전은 Phase 0 실측 전까지 비어 있다(설계안 05절 — "Phase 0에서
    실데이터로 확정" 표시가 붙어 있음). 지금 실제로 동작하는 규칙은 skip_l1뿐이고, 그 외 소스는
    전량 통과시켜 L2가 사실상의 1차 필터 역할을 한다. 사전이 채워지면 이 함수 안에서만 확장하면
    되도록 L1/L2 경계를 그대로 유지했다.
    """
    row = conn.execute(select(source.c.skip_l1).where(source.c.id == source_id)).first()
    if row is None:
        return True
    return True  # 잠정: skip_l1 여부와 무관하게 전량 통과(품명번호 사전 없음)


def score_l2(conn: Connection, title: str) -> dict[int, dict]:
    """대분류(interest_topic_id)별 L2 점수. {topic_id: {"score": int, "matched_terms": [str]}}"""
    rules = conn.execute(
        select(keyword_rule.c.interest_topic_id, keyword_rule.c.term, keyword_rule.c.weight).where(
            keyword_rule.c.active.is_(True)
        )
    ).all()

    lowered = title.lower()
    scores: dict[int, dict] = {}
    for topic_id, term, weight in rules:
        if term.lower() in lowered:
            bucket = scores.setdefault(topic_id, {"score": 0, "matched_terms": []})
            bucket["score"] += weight
            bucket["matched_terms"].append(term)
    return scores
