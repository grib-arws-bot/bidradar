"""S7 고객 관심 주제 관리(U5b, 의사결정_로그 8·9번). 관심도는 조회 시점 계산·캐시 없음
(설계안 08절 공식 그대로) — 고객 수십 곳 규모에서 사전 계산은 재계산 부담만 만든다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Connection

from app.models import (
    customer,
    customer_followed_org,
    customer_interest,
    customer_interest_term,
    interest_topic,
    notice,
    notice_score,
    org,
)

# 스펙에 구체적 수치가 없어 U5b에서 확정. 고객별로 달라져야 하면 그때 customer 컬럼으로 승격.
MIN_SCORE = 30


@dataclass
class InterestDraft:
    topic_ids: list[int] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    followed_org_ids: list[int] = field(default_factory=list)
    price_min: int | None = None
    price_max: int | None = None
    regions: list[str] = field(default_factory=list)


def list_customers(conn: Connection) -> list[dict]:
    rows = conn.execute(
        select(customer.c.id, customer.c.name, customer.c.plan_tier).order_by(customer.c.id)
    ).mappings().all()
    return [dict(r) for r in rows]


def get_topic_catalog(conn: Connection) -> list[dict]:
    rows = conn.execute(
        select(interest_topic.c.id, interest_topic.c.name)
        .where(interest_topic.c.active.is_(True))
        .order_by(interest_topic.c.sort_order)
    ).mappings().all()
    return [dict(r) for r in rows]


def get_interest_profile(conn: Connection, customer_id: int) -> dict | None:
    cust = conn.execute(
        select(customer.c.id, customer.c.name, customer.c.price_min, customer.c.price_max, customer.c.regions).where(
            customer.c.id == customer_id
        )
    ).mappings().first()
    if cust is None:
        return None

    topic_ids = [r[0] for r in conn.execute(
        select(customer_interest.c.interest_topic_id).where(customer_interest.c.customer_id == customer_id)
    )]
    terms = [r[0] for r in conn.execute(
        select(customer_interest_term.c.term).where(customer_interest_term.c.customer_id == customer_id)
    )]
    followed_org_ids = [r[0] for r in conn.execute(
        select(customer_followed_org.c.org_id).where(customer_followed_org.c.customer_id == customer_id)
    )]

    return {
        "customer_id": cust["id"],
        "customer_name": cust["name"],
        "topic_ids": topic_ids,
        "terms": terms,
        "followed_org_ids": followed_org_ids,
        "price_min": int(cust["price_min"]) if cust["price_min"] is not None else None,
        "price_max": int(cust["price_max"]) if cust["price_max"] is not None else None,
        "regions": cust["regions"] or [],
        "topics": get_topic_catalog(conn),
    }


def save_interest_profile(conn: Connection, customer_id: int, draft: InterestDraft) -> None:
    """전체 치환 — 부분 업데이트가 아니라 항상 화면의 현재 상태 전체로 동기화한다."""
    conn.execute(
        update(customer)
        .where(customer.c.id == customer_id)
        .values(price_min=draft.price_min, price_max=draft.price_max, regions=draft.regions or None)
    )

    conn.execute(delete(customer_interest).where(customer_interest.c.customer_id == customer_id))
    for topic_id in draft.topic_ids:
        conn.execute(insert(customer_interest).values(customer_id=customer_id, interest_topic_id=topic_id))

    conn.execute(delete(customer_interest_term).where(customer_interest_term.c.customer_id == customer_id))
    for term in draft.terms:
        if term.strip():
            conn.execute(insert(customer_interest_term).values(customer_id=customer_id, term=term.strip()))

    conn.execute(delete(customer_followed_org).where(customer_followed_org.c.customer_id == customer_id))
    for org_id in draft.followed_org_ids:
        conn.execute(insert(customer_followed_org).values(customer_id=customer_id, org_id=org_id))


def _candidate_notices(conn: Connection) -> list[dict]:
    rows = conn.execute(
        select(
            notice.c.id,
            notice.c.title,
            notice.c.stage,
            notice.c.org_id,
            notice.c.est_price,
            notice.c.region,
            notice.c.open_dt,
            notice.c.close_dt,
            org.c.name.label("org_name"),
        )
        .select_from(notice)
        .join(org, org.c.id == notice.c.org_id, isouter=True)
    ).mappings().all()
    return [dict(r) for r in rows]


def _notice_topic_ids(conn: Connection) -> dict[int, set[int]]:
    mapping: dict[int, set[int]] = {}
    for notice_id, topic_id in conn.execute(select(notice_score.c.notice_id, notice_score.c.interest_topic_id)):
        mapping.setdefault(notice_id, set()).add(topic_id)
    return mapping


def _serialize(n: dict, score: int) -> dict:
    return {
        "id": n["id"],
        "title": n["title"],
        "stage": n["stage"],
        "org_name": n["org_name"],
        "est_price": int(n["est_price"]) if n["est_price"] is not None else None,
        "close_dt": n["close_dt"].isoformat() if n["close_dt"] else None,
        "score": score,
    }


def _score_all(conn: Connection, draft: InterestDraft, *, min_score: int) -> list[tuple[dict, int]]:
    """관심도 공식(설계안 08절)을 조회 시점에 그대로 계산해 전체 매칭 목록을 점수 내림차순으로
    반환한다. compute_matches(미리보기)와 리포트 생성(interest_report.py) 둘 다 이 함수 하나를
    거치므로, "미리보기=실제"·"리포트=실제 매칭"이 항상 같은 계산 결과를 보장한다."""
    notices = _candidate_notices(conn)
    topic_map = _notice_topic_ids(conn)
    topic_id_set = set(draft.topic_ids)
    terms = [t.strip() for t in draft.terms if t.strip()]
    org_id_set = set(draft.followed_org_ids)

    scored: list[tuple[dict, int]] = []
    for n in notices:
        if draft.price_min is not None and (n["est_price"] is None or n["est_price"] < draft.price_min):
            continue
        if draft.price_max is not None and (n["est_price"] is None or n["est_price"] > draft.price_max):
            continue
        if draft.regions and n["region"] not in draft.regions:
            continue

        score = 0
        if topic_id_set and (topic_map.get(n["id"], set()) & topic_id_set):
            score += 30
        if terms and any(t.lower() in n["title"].lower() for t in terms):
            score += 25
        if org_id_set and n["org_id"] in org_id_set:
            score += 20
        if draft.price_min is not None or draft.price_max is not None:
            score += 10
        if draft.regions:
            score += 5
        score = min(score, 100)

        if score < min_score:
            continue
        scored.append((n, score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def compute_matches(conn: Connection, draft: InterestDraft, *, min_score: int = MIN_SCORE) -> dict:
    """S7 미리보기용 — 건수 + 샘플 5건 + 키워드별 최근 30일 매칭 건수."""
    notices = _candidate_notices(conn)
    terms = [t.strip() for t in draft.terms if t.strip()]

    since = datetime.now(timezone.utc) - timedelta(days=30)
    term_counts = {t: 0 for t in terms}
    for n in notices:
        if not n["open_dt"] or n["open_dt"] < since:
            continue
        for t in terms:
            if t.lower() in n["title"].lower():
                term_counts[t] += 1

    scored = _score_all(conn, draft, min_score=min_score)
    return {
        "count": len(scored),
        "samples": [_serialize(n, score) for n, score in scored[:5]],
        "term_counts": term_counts,
    }


def top_matches(conn: Connection, draft: InterestDraft, *, limit: int = 20, min_score: int = MIN_SCORE) -> list[dict]:
    """리포트(뉴스레터) 생성용 — 상위 N건. interest_report.py가 스냅샷을 만들 때 쓴다."""
    scored = _score_all(conn, draft, min_score=min_score)
    return [_serialize(n, score) for n, score in scored[:limit]]


def draft_from_profile(profile: dict) -> InterestDraft:
    """저장된 프로필을 다시 InterestDraft로 — U5b 인수조건("미리보기=저장 후 실제 건수")을
    검증할 때, preview에 넣은 초안과 저장 후 다시 읽은 프로필이 동일한 결과를 내는지 비교한다."""
    return InterestDraft(
        topic_ids=profile["topic_ids"],
        terms=profile["terms"],
        followed_org_ids=profile["followed_org_ids"],
        price_min=profile["price_min"],
        price_max=profile["price_max"],
        regions=profile["regions"],
    )
