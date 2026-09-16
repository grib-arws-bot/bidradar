"""코사인 유사도 기반 관심공고 매칭(2026-09-16, 의사결정_로그 157/158번 후속) — 규칙
매칭(customer_interest.py)과 나란히 비교해보기 위한 신호. 아직 규칙 매칭을 대체하지
않는다 — 같은 후보 풀·같은 하드 필터(customer_interest._candidate_notices·
_passes_hard_filters)를 그대로 재사용해 "점수를 어떻게 매기는가"만 다르게 계산한 뒤,
관리자가 두 방식의 결과를 직접 비교해볼 수 있게 한다(MatchingComparisonPage.tsx).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from app.models import notice
from app.services.customer_interest import InterestDraft, _candidate_notices, _passes_hard_filters, _serialize
from app.services.embeddings import embed_customer_interest_text, embed_texts


def top_matches_cosine(conn: Connection, draft: InterestDraft, profile: dict, *, limit: int = 20) -> dict:
    """규칙 매칭과 동일한 후보 풀·하드 필터를 쓰고, 점수만 코사인 유사도로 낸다.
    notice.embedding이 아직 없는 공고(배치가 덜 끝남)는 이번 비교에서 제외한다 —
    `pending_embeddings`로 그 건수를 같이 반환해 화면에 안내할 수 있게 한다."""
    now = datetime.now(timezone.utc)
    candidates = [n for n in _candidate_notices(conn) if _passes_hard_filters(n, draft, now)]
    candidates_by_id = {n["id"]: n for n in candidates}
    if not candidates_by_id:
        return {"matches": [], "pending_embeddings": 0}

    embedded_count = conn.execute(
        select(func.count())
        .select_from(notice)
        .where(notice.c.id.in_(candidates_by_id.keys()), notice.c.embedding.is_not(None))
    ).scalar_one()
    pending_embeddings = len(candidates_by_id) - embedded_count

    query_text = embed_customer_interest_text(profile)
    query_embedding = embed_texts([query_text])[0]

    distance = notice.c.embedding.cosine_distance(query_embedding)
    rows = conn.execute(
        select(notice.c.id, distance.label("distance"))
        .where(notice.c.id.in_(candidates_by_id.keys()), notice.c.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    ).all()

    matches = []
    for row in rows:
        n = candidates_by_id[row.id]
        # 코사인 거리(0=완전 동일~2=완전 반대)를 유사도 0~100 스케일로 변환 — 규칙 점수(0~100)와
        # 화면 배치는 비슷하게 맞추되, 두 척도가 다르다는 건 필드명(cosine_score)으로 구분한다.
        similarity_pct = round(max(0.0, 1 - row.distance / 2) * 100)
        serialized = _serialize(n, similarity_pct, [])
        serialized["cosine_score"] = serialized.pop("score")
        matches.append(serialized)

    return {"matches": matches, "pending_embeddings": max(pending_embeddings, 0)}
