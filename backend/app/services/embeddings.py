"""코사인 유사도 매칭용 임베딩 계산(2026-09-16, cosine_matching.py가 사용 — 의사결정_로그
157/158번 후속). 관심공고 추천이 규칙(키워드) 매칭 하나뿐이라 "관계없는 것들이 섞인다"는
지적에, 규칙 매칭과 나란히 비교해볼 신호로 임베딩을 추가한다 — 아직 규칙 매칭을 대체하지
않는다.

OpenAI API로 시작하려 했으나 새 벤더 키 발급 마찰이 있어 자체 호스팅(BAAI/bge-m3)으로
전환했다(같은 날, 사용자 지시) — 다국어(한국어 포함) 검색 벤치마크에서 OpenAI
text-embedding-3-small을 앞서는 경우가 많다는 조사 결과도 근거. 모델 가중치는 빌드
시점에 이미지 안에 미리 받아둔다(backend/Dockerfile) — CLAUDE.md "외부 요청은 url_guard
경유" 원칙상 런타임에 Hugging Face Hub로 무가드 다운로드를 할 수 없어서다. 결과적으로
런타임엔 외부 네트워크 의존성이 전혀 없다(장점).

pending_analysis.py(대기건 배치 처리)와 같은 패턴을 그대로 따른다: 후보 조회는 읽기전용
커넥션 하나 + 처리는 공고 하나마다 별도의 짧은 트랜잭션(오래 열린 트랜잭션이 락을 잡아
다른 작업을 막은 2026-09-05 사고 재발 방지).
"""

from __future__ import annotations

import logging
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.db import engine
from app.models import notice, org

logger = logging.getLogger("bidradar.embeddings")

EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_BATCH_LIMIT = 200  # pending_analysis.py와 동일한 상한 원칙 — 무제한 배치 방지


@lru_cache(maxsize=1)
def _model():
    """모델 로딩은 무겁다(수백MB 가중치) — 프로세스당 한 번만 로드해 재사용한다. 첫 호출이
    이 함수를 부르는 스레드에서 로딩까지 같이 걸리므로, 백그라운드 워커 스레드의 첫 호출이
    조금 느릴 수 있다(이후 호출부터는 캐시된 인스턴스를 즉시 반환)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)


def _compute_embeddings(texts: list[str]) -> list[list[float]]:
    """텍스트 목록을 순서 그대로 임베딩 벡터 목록으로 변환한다(정규화된 dense 벡터 —
    코사인 유사도 계산에 바로 쓸 수 있다). 모델 추론 자체가 실패하면 그대로 예외를 던진다
    — 실패해도 흔적 없이 사라지면 안 된다."""
    vectors = _model().encode(texts, normalize_embeddings=True)
    return vectors.tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """비교 API(cosine_matching.py)가 고객 관심사 텍스트 1건을 그때그때 임베딩할 때 쓴다."""
    return _compute_embeddings(texts)


def _notice_embedding_text(title: str, org_name: str | None, region: str | None, stage: str) -> str:
    parts = [title, org_name, region, stage]
    return " · ".join(p for p in parts if p)


def embed_customer_interest_text(profile: dict) -> str:
    """고객이 선택한 관심주제 이름(+우선순위가 normal이 아니면 함께)·커스텀 키워드를 합친
    텍스트 — 이 텍스트의 임베딩과 공고 임베딩의 코사인 유사도로 매칭한다."""
    topic_names = {t["id"]: t["name"] for t in profile.get("topics", [])}
    topic_parts = []
    for topic_id in profile.get("topic_ids", []):
        name = topic_names.get(topic_id)
        if not name:
            continue
        priority = profile.get("topic_priorities", {}).get(topic_id, "normal")
        topic_parts.append(f"{name}({priority})" if priority != "normal" else name)
    return " · ".join(topic_parts + list(profile.get("terms", [])))


def _pending_embedding_notice_ids(conn: Connection, source_id: int | None, limit: int) -> list[int]:
    """아직 임베딩이 없는 공고 id 목록. 무효화된(단계 진행으로 대체된) 공고는 애초에 매칭
    대상이 아니므로(customer_interest._candidate_notices와 동일 기준) 임베딩도 안 만든다.
    source_id는 pending_analysis.py의 _pending_extraction_notice_ids와 동일한 목적(테스트가
    임시 소스 하나로 범위를 좁혀 실제 운영 데이터를 안 건드리게)으로 둔 선택적 필터."""
    stmt = (
        select(notice.c.id)
        .where(notice.c.embedding.is_(None), notice.c.superseded_by_notice_id.is_(None))
        .order_by(notice.c.id)
        .limit(limit)
    )
    if source_id is not None:
        stmt = stmt.where(notice.c.source_id == source_id)
    return conn.execute(stmt).scalars().all()


def embed_one_notice(notice_id: int) -> None:
    """공고 1건의 임베딩을 계산해 저장한다. 자기 트랜잭션 안에서 실행되고, 예외는 이 함수를
    부르는 배치 루프(run_pending_embeddings)가 로그만 남기고 삼킨다 — 공고 하나의 실패가
    나머지 배치를 막으면 안 된다."""
    with engine.begin() as conn:
        row = conn.execute(
            select(notice.c.title, notice.c.region, notice.c.stage, org.c.name.label("org_name"))
            .select_from(notice)
            .join(org, org.c.id == notice.c.org_id, isouter=True)
            .where(notice.c.id == notice_id)
        ).mappings().first()
        if row is None:
            return
        text = _notice_embedding_text(row["title"], row["org_name"], row["region"], row["stage"])
        embedding = _compute_embeddings([text])[0]
        conn.execute(notice.update().where(notice.c.id == notice_id).values(embedding=embedding))


def run_pending_embeddings(source_id: int | None = None, *, batch_limit: int = DEFAULT_BATCH_LIMIT) -> dict:
    """10분마다 도는 run_pending_backlog(app/scheduler.py)에 A1/A2와 나란히 등록해, 아직
    임베딩이 없는 공고를 배치로 채운다."""
    with engine.connect() as conn:
        candidates = _pending_embedding_notice_ids(conn, source_id, batch_limit)

    embedded = 0
    for notice_id in candidates:
        try:
            embed_one_notice(notice_id)
            embedded += 1
        except Exception:  # noqa: BLE001 — 공고 하나의 실패가 나머지 배치를 막으면 안 됨
            logger.exception("공고 임베딩 실패: notice_id=%s", notice_id)
    return {"candidates": len(candidates), "embedded": embedded}
