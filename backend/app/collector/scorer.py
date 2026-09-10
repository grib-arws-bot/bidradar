"""L1 하드필터 + L2 키워드 스코어링(설계안 05절)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.models import keyword_rule, source

L2_PROMOTE_THRESHOLD = 2  # 관심주제 부착 최소 점수. 원래 4(설계안 05절 L2)였으나 공고 1건당
# 관심주제가 사실상 1개만 붙는 문제가 있었다(2026-09-05 사용자 지적, "조금이라도 연관 있으면
# 나오도록") — weight=4(강한 신호, 예: "로봇") 하나만 있어야 통과되던 걸 weight=2(중간 신호)
# 단독으로도 통과하도록 낮춤. weight=1(약한 신호, "구축"·"도입" 등 범용 단어)은 여전히 혼자로는
# 부족하고 두 개는 겹쳐야 한다 — 지나친 오탐(false positive)까지 열어주진 않기 위함.


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


def fetch_active_rules(conn: Connection) -> list[tuple[int, str, int]]:
    """(interest_topic_id, term, weight) 목록 — 공고 여러 건을 한 번에 채점할 때(관심주제
    키워드 재적용 rescan 등) 매번 다시 조회하지 않고 한 번만 가져와 재사용하기 위함."""
    return conn.execute(
        select(keyword_rule.c.interest_topic_id, keyword_rule.c.term, keyword_rule.c.weight).where(
            keyword_rule.c.active.is_(True)
        )
    ).all()


def score_l2(conn: Connection, title: str, *, rules: list[tuple[int, str, int]] | None = None) -> dict[int, dict]:
    """대분류(interest_topic_id)별 L2 점수. {topic_id: {"score": int, "matched_terms": [str]}}"""
    if rules is None:
        rules = fetch_active_rules(conn)

    lowered = title.lower()
    scores: dict[int, dict] = {}
    for topic_id, term, weight in rules:
        if term.lower() in lowered:
            bucket = scores.setdefault(topic_id, {"score": 0, "matched_terms": []})
            bucket["score"] += weight
            bucket["matched_terms"].append(term)
    return scores
