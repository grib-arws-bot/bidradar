"""app/services/embeddings.py 검증 — 코사인 유사도 매칭용 임베딩 배치(2026-09-16, 자체
호스팅 BAAI/bge-m3).

pending_analysis.py의 테스트 패턴(공고 하나마다 별도 트랜잭션 처리)과 동일하게, 실제
커밋된 DB 상태를 다시 조회해 확인한다. 모델 추론은 항상 mock으로 대체 — 이 테스트에서
실제로 무거운 모델을 로딩하지 않는다.
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import notice, org, source
from app.services.embeddings import (
    embed_customer_interest_text,
    embed_one_notice,
    run_pending_embeddings,
)

FAKE_VECTOR = [0.1] * 1024


def _make_temp_source(conn) -> int:
    """공유 개발 DB에 이미 임베딩 안 된 실제 공고가 많을 수 있어(_pending_embedding_notice_ids가
    id 오름차순으로 상한만큼 가져옴), 임시 소스 하나로 범위를 좁혀야 우리가 만든 테스트
    공고가 실제로 배치에 잡힌다 — test_pending_analysis.py와 동일한 패턴."""
    return conn.execute(
        insert(source)
        .values(
            name="테스트 소스(임베딩)", org_name="테스트기관", channel_name="테스트기관",
            base_url="https://example.grib-test.kr/api", stage="입찰공고", adapter_type="openapi",
            frequency_minutes=1440, is_system=False, skip_l1=True, active=True, legal_tier="A",
        )
        .returning(source.c.id)
    ).scalar_one()


def _make_notice(conn, source_id: int, *, embedding=None, superseded_by=None) -> int:
    org_id = conn.execute(insert(org).values(name="테스트발주기관_임베딩").returning(org.c.id)).scalar_one()
    return conn.execute(
        insert(notice).values(
            source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 임베딩 대상 공고",
            org_id=org_id, url="https://example.grib-test.kr/notice/embedding-test",
            embedding=embedding, superseded_by_notice_id=superseded_by,
        ).returning(notice.c.id)
    ).scalar_one()


def _cleanup(source_id: int, notice_ids: list[int]) -> None:
    with engine.begin() as conn:
        conn.execute(delete(notice).where(notice.c.id.in_(notice_ids)))
        conn.execute(delete(org).where(org.c.name == "테스트발주기관_임베딩"))
        conn.execute(delete(source).where(source.c.id == source_id))


def test_embed_one_notice_saves_vector():
    with mock.patch("app.services.embeddings._compute_embeddings", return_value=[FAKE_VECTOR]) as mock_call:
        with engine.begin() as conn:
            source_id = _make_temp_source(conn)
            notice_id = _make_notice(conn, source_id)
        try:
            embed_one_notice(notice_id)
            with engine.connect() as conn:
                saved = conn.execute(select(notice.c.embedding).where(notice.c.id == notice_id)).scalar_one()
            assert saved is not None
            assert len(saved) == 1024
            mock_call.assert_called_once()
        finally:
            _cleanup(source_id, [notice_id])


def test_run_pending_embeddings_skips_already_embedded_and_superseded():
    with mock.patch("app.services.embeddings._compute_embeddings", return_value=[FAKE_VECTOR]) as mock_call:
        with engine.begin() as conn:
            source_id = _make_temp_source(conn)
            pending_id = _make_notice(conn, source_id)
            already_done_id = _make_notice(conn, source_id, embedding=FAKE_VECTOR)
            superseded_id = _make_notice(conn, source_id, superseded_by=already_done_id)
        try:
            result = run_pending_embeddings(source_id, batch_limit=200)

            with engine.connect() as conn:
                pending_embedding = conn.execute(select(notice.c.embedding).where(notice.c.id == pending_id)).scalar_one()
                superseded_embedding = conn.execute(
                    select(notice.c.embedding).where(notice.c.id == superseded_id)
                ).scalar_one()
            assert pending_embedding is not None  # 대기 중이던 건은 채워짐
            assert superseded_embedding is None  # 무효화된 건은 애초에 후보가 아님
            # already_done_id는 이미 임베딩이 있었으므로 다시 호출 안 됨 — 이 소스로 범위를
            # 좁혔으니 정확히 pending_id 1건분만 호출됐어야 한다.
            mock_call.assert_called_once()
            assert result == {"candidates": 1, "embedded": 1}
        finally:
            _cleanup(source_id, [pending_id, already_done_id, superseded_id])


def test_run_pending_embeddings_continues_past_one_failure():
    """공고 하나의 임베딩 계산이 실패해도(모델 오류 등) 나머지 배치는 계속 처리돼야 한다 —
    pending_analysis.py의 "공고 하나 실패가 전체를 막으면 안 된다" 원칙과 동일."""
    with mock.patch(
        "app.services.embeddings._compute_embeddings", side_effect=[RuntimeError("모델 오류"), [FAKE_VECTOR]]
    ):
        with engine.begin() as conn:
            source_id = _make_temp_source(conn)
            failing_id = _make_notice(conn, source_id)
            ok_id = _make_notice(conn, source_id)
        try:
            result = run_pending_embeddings(source_id, batch_limit=200)
            with engine.connect() as conn:
                failing_embedding = conn.execute(select(notice.c.embedding).where(notice.c.id == failing_id)).scalar_one()
                ok_embedding = conn.execute(select(notice.c.embedding).where(notice.c.id == ok_id)).scalar_one()
            assert failing_embedding is None
            assert ok_embedding is not None
            assert result == {"candidates": 2, "embedded": 1}
        finally:
            _cleanup(source_id, [failing_id, ok_id])


def test_embed_customer_interest_text_includes_topics_and_terms():
    profile = {
        "topics": [{"id": 1, "name": "AI/데이터"}, {"id": 2, "name": "로봇/자동화"}],
        "topic_ids": [1, 2],
        "topic_priorities": {1: "high"},
        "terms": ["스마트팜"],
    }
    text = embed_customer_interest_text(profile)
    assert "AI/데이터(high)" in text
    assert "로봇/자동화" in text
    assert "스마트팜" in text


def test_embed_customer_interest_text_includes_profile_summary_when_present():
    profile = {"topics": [], "topic_ids": [], "topic_priorities": {}, "terms": []}
    text = embed_customer_interest_text(profile, "AI 기반 산업안전 CCTV 솔루션을 제공하는 회사")
    assert "AI 기반 산업안전 CCTV 솔루션을 제공하는 회사" in text


def test_embed_customer_interest_text_without_profile_summary_unchanged():
    profile = {"topics": [{"id": 1, "name": "AI/데이터"}], "topic_ids": [1], "topic_priorities": {}, "terms": []}
    assert embed_customer_interest_text(profile) == embed_customer_interest_text(profile, None)
