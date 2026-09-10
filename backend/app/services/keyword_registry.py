"""관심주제 키워드(keyword_rule, 설계안 05절 L2) 관리자 CRUD(2026-09-05 요청) —
지금까지는 seed_constants.py에 하드코딩된 값만 있었고 화면에서 추가할 방법이 없었다.
같은 키워드가 여러 관심주제에 동시에 들어가도 된다(사용자 확인) — unique 제약 없음.

weight_class는 채점에 안 쓰이고(app/collector/scorer.py) 사람이 규칙을 구분하기 위한
표시일 뿐이다(core/tech/ctx/block). 삭제는 다른 레지스트리(source/topic)와 달리 하드
삭제를 허용한다 — keyword_rule.id를 참조하는 다른 테이블이 없어(notice_score.reason은
매칭된 단어를 자유텍스트로만 남길 뿐 FK가 아님) 참조 무결성 문제가 없기 때문."""

from __future__ import annotations

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.collector.scorer import L2_PROMOTE_THRESHOLD, fetch_active_rules, score_l2
from app.models import keyword_rule, notice, notice_score

WEIGHT_CLASSES = ("core", "tech", "ctx", "block")


def list_keywords(conn: Connection, topic_id: int | None = None) -> list[dict]:
    stmt = select(
        keyword_rule.c.id,
        keyword_rule.c.interest_topic_id,
        keyword_rule.c.term,
        keyword_rule.c.weight_class,
        keyword_rule.c.weight,
        keyword_rule.c.active,
    ).order_by(keyword_rule.c.interest_topic_id, keyword_rule.c.id)
    if topic_id is not None:
        stmt = stmt.where(keyword_rule.c.interest_topic_id == topic_id)
    return [dict(r) for r in conn.execute(stmt).mappings().all()]


def create_keyword(
    conn: Connection, *, topic_id: int, term: str, weight_class: str, weight: int
) -> dict:
    if weight_class not in WEIGHT_CLASSES:
        raise ValueError(f"허용되지 않은 weight_class: {weight_class} (허용: {', '.join(WEIGHT_CLASSES)})")
    try:
        row = conn.execute(
            insert(keyword_rule)
            .values(interest_topic_id=topic_id, term=term.strip(), weight_class=weight_class, weight=weight)
            .returning(
                keyword_rule.c.id,
                keyword_rule.c.interest_topic_id,
                keyword_rule.c.term,
                keyword_rule.c.weight_class,
                keyword_rule.c.weight,
                keyword_rule.c.active,
            )
        ).mappings().one()
    except IntegrityError as exc:
        raise ValueError(f"존재하지 않는 관심주제입니다: {topic_id}") from exc
    return dict(row)


def update_keyword(
    conn: Connection,
    keyword_id: int,
    *,
    term: str | None = None,
    weight_class: str | None = None,
    weight: int | None = None,
    active: bool | None = None,
) -> dict | None:
    if weight_class is not None and weight_class not in WEIGHT_CLASSES:
        raise ValueError(f"허용되지 않은 weight_class: {weight_class} (허용: {', '.join(WEIGHT_CLASSES)})")
    values = {
        k: v
        for k, v in {"term": term.strip() if term else None, "weight_class": weight_class, "weight": weight, "active": active}.items()
        if v is not None
    }
    if not values:
        row = conn.execute(select(keyword_rule).where(keyword_rule.c.id == keyword_id)).mappings().first()
        return dict(row) if row else None
    row = conn.execute(
        update(keyword_rule)
        .where(keyword_rule.c.id == keyword_id)
        .values(**values)
        .returning(
            keyword_rule.c.id,
            keyword_rule.c.interest_topic_id,
            keyword_rule.c.term,
            keyword_rule.c.weight_class,
            keyword_rule.c.weight,
            keyword_rule.c.active,
        )
    ).mappings().first()
    return dict(row) if row else None


def delete_keyword(conn: Connection, keyword_id: int) -> bool:
    result = conn.execute(delete(keyword_rule).where(keyword_rule.c.id == keyword_id))
    return result.rowcount > 0


def rescan_notice_scores(conn: Connection) -> dict:
    """키워드를 추가·수정한 뒤 관리자가 수동으로 실행 — 이미 수집된 공고에도 새 규칙을
    소급 적용한다(자동 실행 없음, S8 원칙 3과 같은 이유: 규칙 변경은 사람이 트리거).
    이미 있는 (notice_id, topic_id) 조합은 절대 건드리지 않는다 — 수동 분류검수·기존 매칭을
    덮어쓰거나 지우지 않고, 새로 통과하는 조합만 추가한다(순수 추가, 제거 없음)."""
    existing_pairs = set(
        conn.execute(select(notice_score.c.notice_id, notice_score.c.interest_topic_id)).all()
    )
    rows = conn.execute(select(notice.c.id, notice.c.title)).all()
    rules = fetch_active_rules(conn)

    added = 0
    for notice_id, title in rows:
        for topic_id, info in score_l2(conn, title, rules=rules).items():
            if info["score"] < L2_PROMOTE_THRESHOLD:
                continue
            if (notice_id, topic_id) in existing_pairs:
                continue
            conn.execute(
                insert(notice_score).values(
                    notice_id=notice_id,
                    interest_topic_id=topic_id,
                    l2_score=info["score"],
                    reason=f"키워드 매칭: {', '.join(info['matched_terms'])}",
                    rule_ver=1,
                )
            )
            existing_pairs.add((notice_id, topic_id))
            added += 1

    return {"scanned": len(rows), "added": added}
