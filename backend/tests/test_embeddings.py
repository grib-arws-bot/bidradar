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
from app.models import analysis, analysis_doc, notice, org, source
from app.services.embeddings import (
    A1_TEXT_MAX_CHARS,
    _latest_attachment_text,
    _notice_embedding_text,
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


def _make_notice(conn, source_id: int, *, embedding=None, embedding_a1=None, superseded_by=None) -> int:
    org_id = conn.execute(insert(org).values(name="테스트발주기관_임베딩").returning(org.c.id)).scalar_one()
    return conn.execute(
        insert(notice).values(
            source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 임베딩 대상 공고",
            org_id=org_id, url="https://example.grib-test.kr/notice/embedding-test",
            embedding=embedding, embedding_a1=embedding_a1, superseded_by_notice_id=superseded_by,
        ).returning(notice.c.id)
    ).scalar_one()


def _cleanup(source_id: int, notice_ids: list[int]) -> None:
    with engine.begin() as conn:
        # analysis.notice_id는 ondelete 지정이 없어(RESTRICT) notice보다 먼저 지워야 한다
        # (analysis_doc은 analysis에 CASCADE라 analysis만 지우면 같이 지워짐).
        conn.execute(delete(analysis).where(analysis.c.notice_id.in_(notice_ids)))
        conn.execute(delete(notice).where(notice.c.id.in_(notice_ids)))
        conn.execute(delete(org).where(org.c.name == "테스트발주기관_임베딩"))
        conn.execute(delete(source).where(source.c.id == source_id))


def _make_analysis_with_doc(conn, notice_id: int, *, text: str | None, extract_ok: bool = True, ver: int = 1) -> int:
    analysis_id = conn.execute(
        insert(analysis)
        .values(notice_id=notice_id, source_kind="notice", input_ref="test", ver=ver)
        .returning(analysis.c.id)
    ).scalar_one()
    conn.execute(
        insert(analysis_doc).values(
            analysis_id=analysis_id, name="test.hwp", kind="hwp", bytes=100, sha256="x" * 64,
            extract_ok=extract_ok, text=text,
        )
    )
    return analysis_id


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


def test_embed_one_notice_attachment_variant_saves_to_embedding_a1_column():
    with mock.patch("app.services.embeddings._compute_embeddings", return_value=[FAKE_VECTOR]):
        with engine.begin() as conn:
            source_id = _make_temp_source(conn)
            notice_id = _make_notice(conn, source_id)
        try:
            embed_one_notice(notice_id, variant="attachment")
            with engine.connect() as conn:
                row = conn.execute(
                    select(notice.c.embedding, notice.c.embedding_a1).where(notice.c.id == notice_id)
                ).one()
            assert row.embedding is None  # title variant 컬럼은 안 건드림
            assert row.embedding_a1 is not None
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
    pending_analysis.py의 "공고 하나 실패가 전체를 막으면 안 된다" 원칙과 동일.

    2026-09-19 — 배치 인코딩 도입 후: 청크 전체를 한 번에 인코딩 시도하고(1번째 side_effect,
    실패) 실패하면 embed_one_notice로 공고 하나씩 순차 재시도한다(2·3번째 side_effect) —
    그중 failing_id만 계속 실패하게 해서 격리가 실제로 되는지 확인한다."""
    with mock.patch(
        "app.services.embeddings._compute_embeddings",
        side_effect=[RuntimeError("배치 실패"), RuntimeError("모델 오류"), [FAKE_VECTOR]],
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


def test_run_pending_embeddings_encodes_multiple_notices_in_one_model_call():
    """2026-09-19 — title(제목 등 짧은 텍스트)을 공고 하나씩 개별 인코딩하면 CPU에서 배치
    연산 이점을 못 살려 느렸다(embedding_a1 전량 재계산 백필 중 실측). 여러 건을 한 번의
    _compute_embeddings() 호출로 묶어 처리하는지(=모델 호출 횟수가 공고 수보다 훨씬
    적은지) 검증한다 — title variant는 배치화가 확실히 도움됨을 실측으로 확인했다."""
    with mock.patch(
        "app.services.embeddings._compute_embeddings", return_value=[FAKE_VECTOR] * 3
    ) as mock_compute:
        with engine.begin() as conn:
            source_id = _make_temp_source(conn)
            notice_ids = [_make_notice(conn, source_id) for _ in range(3)]
        try:
            result = run_pending_embeddings(source_id, batch_limit=200)
            assert result == {"candidates": 3, "embedded": 3}
            # title의 배치 크기(16)보다 적은 3건이므로 한 번의 호출로 다 묶여야 함
            assert mock_compute.call_count == 1
            assert len(mock_compute.call_args.args[0]) == 3
            with engine.connect() as conn:
                embeddings = conn.execute(
                    select(notice.c.embedding).where(notice.c.id.in_(notice_ids))
                ).scalars().all()
            assert all(e is not None for e in embeddings)
        finally:
            _cleanup(source_id, notice_ids)


def test_run_pending_embeddings_does_not_batch_attachment_variant():
    """2026-09-19 — attachment(첨부 전문, 최대 4000자)를 title과 같은 배치 크기(16)로
    묶었더니 실전 배포에서 오히려 느려졌다(건당 8~16초 -> 24~32초, 6.5분 넘게 걸림) —
    sentence-transformers가 배치 안 최장 시퀀스에 맞춰 짧은 텍스트도 패딩해서, 길이가
    들쭉날쭉한 attachment는 크게 묶을수록 연산 낭비가 커진 것으로 보인다. 그 실측 이후
    attachment는 배치화 이전(공고당 모델 호출 1회)으로 되돌렸다 — 회귀 방지 테스트."""
    with mock.patch(
        "app.services.embeddings._compute_embeddings", return_value=[FAKE_VECTOR]
    ) as mock_compute:
        with engine.begin() as conn:
            source_id = _make_temp_source(conn)
            notice_ids = [_make_notice(conn, source_id) for _ in range(3)]
        try:
            result = run_pending_embeddings(source_id, batch_limit=200, variant="attachment")
            assert result == {"candidates": 3, "embedded": 3}
            # title과 달리 attachment는 한 번에 묶지 않고 공고마다 별도 호출해야 함
            assert mock_compute.call_count == 3
            for call in mock_compute.call_args_list:
                assert len(call.args[0]) == 1
        finally:
            _cleanup(source_id, notice_ids)


def test_run_pending_embeddings_attachment_variant_is_independent_of_title_variant():
    """title 컬럼이 이미 채워져 있어도 attachment 컬럼은 별도로 대기 후보에 잡혀야 한다 —
    두 variant가 서로 독립적으로 채워진다는 설계의 핵심 전제."""
    with mock.patch("app.services.embeddings._compute_embeddings", return_value=[FAKE_VECTOR]):
        with engine.begin() as conn:
            source_id = _make_temp_source(conn)
            notice_id = _make_notice(conn, source_id, embedding=FAKE_VECTOR)  # title은 이미 완료
        try:
            result = run_pending_embeddings(source_id, batch_limit=200, variant="attachment")
            assert result == {"candidates": 1, "embedded": 1}
            with engine.connect() as conn:
                embedding_a1 = conn.execute(
                    select(notice.c.embedding_a1).where(notice.c.id == notice_id)
                ).scalar_one()
            assert embedding_a1 is not None
        finally:
            _cleanup(source_id, [notice_id])


def test_notice_embedding_text_includes_attachment_text_when_present():
    text = _notice_embedding_text("제목", "발주기관", "서울", "입찰공고", "첨부파일 본문 내용")
    assert "첨부파일 본문 내용" in text
    assert "제목" in text


def test_notice_embedding_text_without_attachment_text_unchanged():
    assert _notice_embedding_text("제목", "발주기관", "서울", "입찰공고") == _notice_embedding_text(
        "제목", "발주기관", "서울", "입찰공고", None
    )


def test_latest_attachment_text_excludes_failed_extractions():
    with engine.begin() as conn:
        source_id = _make_temp_source(conn)
        notice_id = _make_notice(conn, source_id)
        _make_analysis_with_doc(conn, notice_id, text="실패한 추출 흔적", extract_ok=False)
    try:
        with engine.connect() as conn:
            assert _latest_attachment_text(conn, notice_id) is None
    finally:
        _cleanup(source_id, [notice_id])


def test_latest_attachment_text_truncates_to_budget():
    with engine.begin() as conn:
        source_id = _make_temp_source(conn)
        notice_id = _make_notice(conn, source_id)
        _make_analysis_with_doc(conn, notice_id, text="가" * (A1_TEXT_MAX_CHARS + 500))
    try:
        with engine.connect() as conn:
            result = _latest_attachment_text(conn, notice_id)
        assert len(result) == A1_TEXT_MAX_CHARS
    finally:
        _cleanup(source_id, [notice_id])


def test_latest_attachment_text_uses_latest_analysis_version():
    """재분석(ver 증가)이 있으면 예전 버전의 첨부 텍스트가 아니라 최신 버전만 써야 한다."""
    with engine.begin() as conn:
        source_id = _make_temp_source(conn)
        notice_id = _make_notice(conn, source_id)
        _make_analysis_with_doc(conn, notice_id, text="예전 버전 내용", ver=1)
        _make_analysis_with_doc(conn, notice_id, text="최신 버전 내용", ver=2)
    try:
        with engine.connect() as conn:
            result = _latest_attachment_text(conn, notice_id)
        assert result == "최신 버전 내용"
    finally:
        _cleanup(source_id, [notice_id])


def test_embed_one_notice_attachment_variant_includes_attachment_text_in_embedded_text():
    with mock.patch("app.services.embeddings._compute_embeddings", return_value=[FAKE_VECTOR]) as mock_call:
        with engine.begin() as conn:
            source_id = _make_temp_source(conn)
            notice_id = _make_notice(conn, source_id)
            _make_analysis_with_doc(conn, notice_id, text="공고문 첨부의 실제 사업 내용")
        try:
            embed_one_notice(notice_id, variant="attachment")
            embedded_text = mock_call.call_args[0][0][0]
            assert "공고문 첨부의 실제 사업 내용" in embedded_text
        finally:
            _cleanup(source_id, [notice_id])


def test_embed_one_notice_title_variant_does_not_include_attachment_text():
    """variant="title"(기본값)은 A1 텍스트가 있어도 무시해야 한다 — "제목만" 비교 기준이
    흔들리면 안 된다."""
    with mock.patch("app.services.embeddings._compute_embeddings", return_value=[FAKE_VECTOR]) as mock_call:
        with engine.begin() as conn:
            source_id = _make_temp_source(conn)
            notice_id = _make_notice(conn, source_id)
            _make_analysis_with_doc(conn, notice_id, text="이 텍스트는 title variant에 섞이면 안 됨")
        try:
            embed_one_notice(notice_id)
            embedded_text = mock_call.call_args[0][0][0]
            assert "이 텍스트는 title variant에 섞이면 안 됨" not in embedded_text
        finally:
            _cleanup(source_id, [notice_id])


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
