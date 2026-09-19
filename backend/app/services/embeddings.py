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

2026-09-17 — 매칭 방식 비교 화면에서 규칙 매칭과 코사인(제목만) 매칭의 일치율이 20건 중
2~3건뿐이라는 지적이 나와 봤더니, 규칙 매칭은 이미 A1 첨부 전체 추출 텍스트로 재채점하는데
(rule_ver=2, notice_topic_scoring.py) 코사인은 제목·발주기관·지역·단계만 봐서 정보량 차이가
컸다. A1 텍스트를 더한 두 번째 임베딩(notice.embedding_a1)을 추가해 규칙/코사인-제목/
코사인-첨부 3방향 비교가 가능하게 한다 — 기존 embedding 컬럼은 덮어쓰지 않는다(덮어쓰면
"제목만" 결과가 사라져 비교 자체가 안 됨). 아래 함수들은 `variant` 인자로 두 컬럼을 같은
코드 경로로 처리한다.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.sql import ColumnElement

from app.db import engine
from app.models import analysis, analysis_doc, notice, org

logger = logging.getLogger("bidradar.embeddings")

EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_BATCH_LIMIT = 200  # pending_analysis.py와 동일한 상한 원칙 — 무제한 배치 방지
# 2026-09-19 — 공고를 하나씩 개별 인코딩하면(_compute_embeddings([text])) CPU에서 배치
# 연산 이점을 전혀 못 살려 건당 8~16초가 걸렸다(embedding_a1 전량 재계산 백필 중 실측 —
# 나라장터가 하루 수백 건씩 올라오는 걸 감안하면 이 페이스로는 못 따라잡음). 여러 건을
# 묶어 한 번의 모델 호출로 인코딩한다 — DEFAULT_BATCH_LIMIT(한 번의 run_pending_embeddings
# 호출이 훑는 대기열 크기)과는 다른 값, 이건 그중 실제 모델 호출 한 번에 묶는 개수.
EMBEDDING_ENCODE_BATCH_SIZE = 16
# bge-m3 컨텍스트 한도(8192 토큰) 안에서 여유 있게 문서 앞부분 위주로만 담는다 — 전문을
# 다 넣진 않는다.
A1_TEXT_MAX_CHARS = 4000

Variant = Literal["title", "attachment"]


def _embedding_column(variant: Variant) -> ColumnElement:
    return notice.c.embedding_a1 if variant == "attachment" else notice.c.embedding


def _embedded_at_column(variant: Variant) -> ColumnElement:
    return notice.c.embedded_a1_at if variant == "attachment" else notice.c.embedded_at


@lru_cache(maxsize=1)
def _model():
    """모델 로딩은 무겁다(수백MB 가중치) — 프로세스당 한 번만 로드해 재사용한다. 첫 호출이
    이 함수를 부르는 스레드에서 로딩까지 같이 걸리므로, 백그라운드 워커 스레드의 첫 호출이
    조금 느릴 수 있다(이후 호출부터는 캐시된 인스턴스를 즉시 반환)."""
    from sentence_transformers import SentenceTransformer

    # 2026-09-17 -- model.safetensors는 BAAI/bge-m3의 main 리비전엔 없는 파일이고, 허깅페이스가
    # 온라인에서만 조회 가능한 별도 자동 변환 리비전으로 제공하는 것뿐이다(실제 컨테이너
    # 실행으로 확인 -- HF_HUB_OFFLINE=1인 이 런타임에서 그 리비전을 못 찾아 로딩이 실패했다).
    # Dockerfile이 정식 main 파일인 pytorch_model.bin만 받아두므로 여기서도 그것만 쓰도록
    # 명시한다 -- use_safetensors=True로 두면 오프라인에서 매번 이 실패가 재현된다.
    return SentenceTransformer(EMBEDDING_MODEL, model_kwargs={"use_safetensors": False})


def _compute_embeddings(texts: list[str]) -> list[list[float]]:
    """텍스트 목록을 순서 그대로 임베딩 벡터 목록으로 변환한다(정규화된 dense 벡터 —
    코사인 유사도 계산에 바로 쓸 수 있다). 모델 추론 자체가 실패하면 그대로 예외를 던진다
    — 실패해도 흔적 없이 사라지면 안 된다."""
    vectors = _model().encode(texts, normalize_embeddings=True)
    return vectors.tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """비교 API(cosine_matching.py)가 고객 관심사 텍스트 1건을 그때그때 임베딩할 때 쓴다."""
    return _compute_embeddings(texts)


def _notice_embedding_text(
    title: str, org_name: str | None, region: str | None, stage: str, attachment_text: str | None = None
) -> str:
    parts = [title, org_name, region, stage]
    text = " · ".join(p for p in parts if p)
    if attachment_text:
        text = f"{text}\n\n{attachment_text}"
    return text


def _latest_attachment_text(conn: Connection, notice_id: int) -> str | None:
    """이 공고의 가장 최근 분석(analysis, ver 최대)에서 A1이 성공적으로 추출한 첨부 텍스트를
    모아 반환한다. 실패한 추출(extract_ok=false)은 제외 — 에러 메시지나 빈 내용이 임베딩에
    섞이면 안 된다. 분석 이력이 없으면(아직 A1을 안 돌렸으면) None."""
    latest_analysis_id = conn.execute(
        select(analysis.c.id)
        .where(analysis.c.notice_id == notice_id)
        .order_by(analysis.c.ver.desc(), analysis.c.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest_analysis_id is None:
        return None
    texts = conn.execute(
        select(analysis_doc.c.text)
        .where(
            analysis_doc.c.analysis_id == latest_analysis_id,
            analysis_doc.c.extract_ok.is_(True),
            analysis_doc.c.text.is_not(None),
        )
    ).scalars().all()
    if not texts:
        return None
    return "\n\n".join(texts)[:A1_TEXT_MAX_CHARS]


def embed_customer_interest_text(profile: dict, profile_summary_md: str | None = None) -> str:
    """고객이 선택한 관심주제 이름(+우선순위가 normal이 아니면 함께)·커스텀 키워드·
    (있다면) AI 프로필 요약을 합친 텍스트 — 이 텍스트의 임베딩과 공고 임베딩의 코사인
    유사도로 매칭한다.

    2026-09-17 -- 프로필 요약(customer.profile_summary_md, 소개서 기반 LLM 요약)은 이미
    존재하는데 이제껏 어떤 매칭 경로에서도 안 쓰였다 -- 관심주제 몇 개·키워드 몇 단어보다
    훨씬 풍부한 신호라 우선순위를 높여 반영한다(사용자 지시). 관심주제/키워드가 아예 없는
    고객도 소개서만 있으면 의미 있는 매칭이 가능해진다."""
    topic_names = {t["id"]: t["name"] for t in profile.get("topics", [])}
    topic_parts = []
    for topic_id in profile.get("topic_ids", []):
        name = topic_names.get(topic_id)
        if not name:
            continue
        priority = profile.get("topic_priorities", {}).get(topic_id, "normal")
        topic_parts.append(f"{name}({priority})" if priority != "normal" else name)
    text = " · ".join(topic_parts + list(profile.get("terms", [])))
    if profile_summary_md:
        text = f"{text}\n\n{profile_summary_md}" if text else profile_summary_md
    return text


def _pending_embedding_notice_ids(
    conn: Connection, source_id: int | None, limit: int, *, variant: Variant = "title"
) -> list[int]:
    """아직 해당 variant 임베딩이 없는 공고 id 목록. 무효화된(단계 진행으로 대체된) 공고는
    애초에 매칭 대상이 아니므로(customer_interest._candidate_notices와 동일 기준) 임베딩도
    안 만든다. source_id는 pending_analysis.py의 _pending_extraction_notice_ids와 동일한
    목적(테스트가 임시 소스 하나로 범위를 좁혀 실제 운영 데이터를 안 건드리게)으로 둔 선택적
    필터."""
    stmt = (
        select(notice.c.id)
        .where(_embedding_column(variant).is_(None), notice.c.superseded_by_notice_id.is_(None))
        .order_by(notice.c.id)
        .limit(limit)
    )
    if source_id is not None:
        stmt = stmt.where(notice.c.source_id == source_id)
    return conn.execute(stmt).scalars().all()


def embed_one_notice(notice_id: int, *, variant: Variant = "title") -> None:
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
        attachment_text = _latest_attachment_text(conn, notice_id) if variant == "attachment" else None
        text = _notice_embedding_text(row["title"], row["org_name"], row["region"], row["stage"], attachment_text)
        embedding = _compute_embeddings([text])[0]
        conn.execute(
            notice.update()
            .where(notice.c.id == notice_id)
            .values(**{_embedding_column(variant).name: embedding, _embedded_at_column(variant).name: func.now()})
        )


def _embed_notice_chunk(notice_ids: list[int], *, variant: Variant) -> int:
    """여러 공고를 한 번의 모델 호출로 인코딩한다(embed_one_notice를 반복 호출하는 대신) —
    CPU에서 배치 크기가 클수록 벡터 연산 효율이 오른다. 메타데이터 조회는 읽기전용
    커넥션으로, 실제 DB 갱신은 인코딩이 끝난 뒤 별도의 짧은 트랜잭션으로 한다 — 오래 열린
    트랜잭션이 락을 잡는 문제(2026-09-05 사고, 위 모듈 docstring 참고)는 그대로 피한다
    (느린 model.encode() 호출 동안 트랜잭션을 열어두지 않음).

    배치 인코딩 자체가 실패하면(모델 오류 등) embed_one_notice로 하나씩 순차 재시도해
    어떤 공고가 문제인지 격리한다 — "공고 하나의 실패가 나머지를 막으면 안 된다"는 기존
    원칙은 그대로 유지."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(notice.c.id, notice.c.title, notice.c.region, notice.c.stage, org.c.name.label("org_name"))
            .select_from(notice)
            .join(org, org.c.id == notice.c.org_id, isouter=True)
            .where(notice.c.id.in_(notice_ids))
        ).mappings().all()
        texts_by_id: dict[int, str] = {}
        for row in rows:
            attachment_text = _latest_attachment_text(conn, row["id"]) if variant == "attachment" else None
            texts_by_id[row["id"]] = _notice_embedding_text(
                row["title"], row["org_name"], row["region"], row["stage"], attachment_text
            )

    ids = [nid for nid in notice_ids if nid in texts_by_id]
    if not ids:
        return 0

    try:
        vectors = _compute_embeddings([texts_by_id[nid] for nid in ids])
    except Exception:  # noqa: BLE001 — 배치 하나가 통째로 실패해도 개별 재시도로 복구를 시도
        logger.exception("배치 임베딩 실패(variant=%s, %d건) — 개별 재시도로 전환", variant, len(ids))
        embedded = 0
        for notice_id in ids:
            try:
                embed_one_notice(notice_id, variant=variant)
                embedded += 1
            except Exception:  # noqa: BLE001 — 공고 하나의 실패가 나머지를 막으면 안 됨
                logger.exception("공고 임베딩 실패: notice_id=%s variant=%s", notice_id, variant)
        return embedded

    with engine.begin() as conn:
        for notice_id, vector in zip(ids, vectors):
            conn.execute(
                notice.update()
                .where(notice.c.id == notice_id)
                .values(**{_embedding_column(variant).name: vector, _embedded_at_column(variant).name: func.now()})
            )
    return len(ids)


def run_pending_embeddings(
    source_id: int | None = None, *, batch_limit: int = DEFAULT_BATCH_LIMIT, variant: Variant = "title"
) -> dict:
    """10분마다 도는 run_pending_backlog(app/scheduler.py)에 A1/A2와 나란히 등록해, 아직
    임베딩이 없는 공고를 배치로 채운다. variant="title"과 "attachment" 둘 다 같은 주기로
    따로 호출돼(app/scheduler.py) 두 컬럼이 독립적으로 채워진다."""
    with engine.connect() as conn:
        candidates = _pending_embedding_notice_ids(conn, source_id, batch_limit, variant=variant)

    embedded = 0
    for i in range(0, len(candidates), EMBEDDING_ENCODE_BATCH_SIZE):
        chunk = candidates[i : i + EMBEDDING_ENCODE_BATCH_SIZE]
        embedded += _embed_notice_chunk(chunk, variant=variant)
    return {"candidates": len(candidates), "embedded": embedded}
