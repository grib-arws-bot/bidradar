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

from app.models import customer, notice
from app.services.customer_interest import InterestDraft, _candidate_notices, _passes_hard_filters, _serialize
from app.services.embeddings import Variant, _embedding_column, embed_customer_interest_text, embed_texts


def _query_embedding_for_profile(conn: Connection, profile: dict) -> list[float]:
    """고객의 관심주제·키워드·(있으면) AI 프로필 요약을 합친 텍스트를 임베딩한다.
    2026-09-17 -- 관심주제/키워드보다 풍부한 신호인 AI 프로필 요약(소개서 기반)을 여기서만
    조회해 합친다. get_interest_profile()의 일반 프로필 응답(관심주제 설정 화면이 그대로
    받아쓰는 것)에는 안 넣는다 -- 그 화면은 이 텍스트가 필요 없고, 요약이 길면 그 화면의
    응답만 불필요하게 커진다."""
    profile_summary_md = conn.execute(
        select(customer.c.profile_summary_md).where(customer.c.id == profile["customer_id"])
    ).scalar_one_or_none()
    query_text = embed_customer_interest_text(profile, profile_summary_md)
    return embed_texts([query_text])[0]


def _cosine_similarities(
    conn: Connection, notice_ids: list[int], embedding_col, query_embedding: list[float]
) -> dict[int, float]:
    """주어진 컬럼(embedding/embedding_a1) 기준 코사인 유사도(0~1, 1이 완전 동일)를
    임베딩이 채워진 공고에 대해서만 반환한다 — 아직 안 채워진 공고는 결과에서 아예 빠진다
    (호출부가 "값 없음"으로 구분해서 처리)."""
    if not notice_ids:
        return {}
    distance = embedding_col.cosine_distance(query_embedding)
    rows = conn.execute(
        select(notice.c.id, distance.label("distance"))
        .where(notice.c.id.in_(notice_ids), embedding_col.is_not(None))
    ).all()
    # 코사인 거리(0=완전 동일~2=완전 반대)를 유사도 0~1로 변환.
    return {row.id: max(0.0, 1 - row.distance / 2) for row in rows}


def weighted_cosine_scores(
    conn: Connection,
    notice_ids: list[int],
    query_embedding: list[float],
    *,
    w_title: float = 0.6,
    w_attach: float = 0.4,
) -> dict[int, float | None]:
    """제목만 임베딩(notice.embedding)과 제목+첨부 임베딩(notice.embedding_a1)을 가중
    결합한다(2026-09-21, 의사결정_로그 192번) — 첨부문서가 길면 dense 임베딩 특성상 제목의
    상대적 비중이 희석되는데, 둘을 이미 별도 컬럼으로 갖고 있으니 새로 임베딩을 계산하지
    않고 가중치만 준다. 한쪽 임베딩이 아직 없으면 있는 쪽만으로 정규화하고, 둘 다 없으면
    None(신호 없음 — 호출부가 noisy-OR 결합에서 제외해야 함)."""
    title_sims = _cosine_similarities(conn, notice_ids, notice.c.embedding, query_embedding)
    attach_sims = _cosine_similarities(conn, notice_ids, notice.c.embedding_a1, query_embedding)

    scores: dict[int, float | None] = {}
    for notice_id in notice_ids:
        title_sim = title_sims.get(notice_id)
        attach_sim = attach_sims.get(notice_id)
        if title_sim is None and attach_sim is None:
            scores[notice_id] = None
        elif attach_sim is None:
            scores[notice_id] = title_sim
        elif title_sim is None:
            scores[notice_id] = attach_sim
        else:
            scores[notice_id] = w_title * title_sim + w_attach * attach_sim
    return scores


def top_matches_cosine(
    conn: Connection, draft: InterestDraft, profile: dict, *, limit: int = 20, variant: Variant = "title"
) -> dict:
    """규칙 매칭과 동일한 후보 풀·하드 필터를 쓰고, 점수만 코사인 유사도로 낸다.
    variant="title"은 제목·발주기관·지역·단계만, "attachment"는 A1 첨부 전체 추출 텍스트까지
    반영한 임베딩(notice.embedding_a1)을 쓴다(2026-09-17 — 규칙 매칭과의 일치율이 너무 낮다는
    지적에, 규칙 매칭이 이미 첨부 텍스트를 보고 있어 정보량 차이가 원인이었음을 확인하고
    추가). 해당 variant의 임베딩이 아직 없는 공고(배치가 덜 끝남)는 이번 비교에서 제외한다 —
    `pending_embeddings`로 그 건수를 같이 반환해 화면에 안내할 수 있게 한다."""
    now = datetime.now(timezone.utc)
    candidates = [n for n in _candidate_notices(conn) if _passes_hard_filters(n, draft, now)]
    candidates_by_id = {n["id"]: n for n in candidates}
    if not candidates_by_id:
        return {"matches": [], "pending_embeddings": 0}

    embedding_col = _embedding_column(variant)
    embedded_count = conn.execute(
        select(func.count())
        .select_from(notice)
        .where(notice.c.id.in_(candidates_by_id.keys()), embedding_col.is_not(None))
    ).scalar_one()
    pending_embeddings = len(candidates_by_id) - embedded_count

    query_embedding = _query_embedding_for_profile(conn, profile)
    similarities = _cosine_similarities(conn, list(candidates_by_id.keys()), embedding_col, query_embedding)
    top_ids = sorted(similarities, key=lambda nid: similarities[nid], reverse=True)[:limit]

    matches = []
    for notice_id in top_ids:
        n = candidates_by_id[notice_id]
        # 유사도(0~1)를 규칙 점수(0~100)와 화면 배치가 비슷하도록 0~100 스케일로 변환 —
        # 두 척도가 다르다는 건 필드명(cosine_score)으로 구분한다.
        serialized = _serialize(n, round(similarities[notice_id] * 100), [])
        serialized["cosine_score"] = serialized.pop("score")
        matches.append(serialized)

    return {"matches": matches, "pending_embeddings": max(pending_embeddings, 0)}
