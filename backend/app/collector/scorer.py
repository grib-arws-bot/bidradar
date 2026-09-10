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


# 제목에 나온 용어는 첨부문서 본문에 우연히 몇 번 더 나오는 것보다 훨씬 의도적인 신호다 —
# 제목 1회 등장을 본문 5회 등장과 동급으로 친다(2026-09-10 사용자 확정 — "제목에서의 키워드는
# 가중치를 높여서 산정해"). 값 자체는 조정 가능한 상수.
TITLE_OCCURRENCE_WEIGHT = 5


def score_topics_weighted(
    conn: Connection | None = None,
    *,
    title: str,
    document_text: str = "",
    rules: list[tuple[int, str, int]] | None = None,
) -> dict[int, dict]:
    """제목 + 첨부문서 본문에서 키워드가 **몇 번** 나오는지로 관심주제별 점수를 계산한다
    (2026-09-10 사용자 지시 — "추출된 텍스트에서 키워드들이 얼마나 나오는지를 검출"). score_l2는
    제목 전용이라 용어가 있는지(0/1)만 보면 충분했지만, 첨부문서는 분량이 훨씬 커서 등장
    횟수 자체가 실제 관련도를 더 잘 드러낸다는 판단 — 여전히 규칙 기반이고 LLM은 쓰지 않는다
    (CLAUDE.md S8 원칙 1과 같은 방향, app/services/notice_topic_scoring.py에서 첨부분석(A1)
    성공 직후 호출). rules를 직접 넘기면 conn 없이도(단위 테스트 등) 순수 함수로 쓸 수 있다."""
    if rules is None:
        if conn is None:
            raise ValueError("rules를 안 주면 conn이 있어야 keyword_rule을 조회할 수 있습니다.")
        rules = fetch_active_rules(conn)

    title_lower = title.lower()
    doc_lower = document_text.lower()
    scores: dict[int, dict] = {}
    for topic_id, term, weight in rules:
        term_lower = term.lower()
        title_count = title_lower.count(term_lower)
        doc_count = doc_lower.count(term_lower)
        total_count = title_count + doc_count
        if total_count == 0:
            continue
        occurrence = title_count * TITLE_OCCURRENCE_WEIGHT + doc_count
        bucket = scores.setdefault(topic_id, {"score": 0, "matched_terms": []})
        bucket["score"] += weight * occurrence
        bucket["matched_terms"].append(f"{term}×{total_count}")
    return scores
