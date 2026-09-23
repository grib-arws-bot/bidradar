"""사내 sLLM(C, classify-doc) 과거 데이터 백필 — app/services/analysis/sllm_doc_backfill.py
검증(2026-09-20, 의사결정_로그 182번 — CLI 1회성 명령에서 스케줄러 상시 배치로 재설계).
실제 sLLM 서버에 나가지 않는다 — classify_doc을 모킹해서 재분류·checked_at 기록·개별
실패 격리·연결 장애 시 배치 중단만 확인한다.
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

import pytest
import requests
from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import analysis, analysis_doc, notice, source
from app.services.analysis.sllm_doc_backfill import run_pending_sllm_doc_backfill
from app.services.sllm_client import SllmError, SllmNotConfiguredError


def _any_source_id(conn) -> int:
    return conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()


@pytest.fixture
def two_docs():
    """추출 완료된 문서 2건(공통문서 후보 1건 + 진짜 규격서 1건)을 흉내 낸다."""
    with engine.begin() as conn:
        notice_id = conn.execute(
            insert(notice).values(
                source_id=_any_source_id(conn), source_ver=1, stage="입찰공고", title="[테스트] sLLM 문서 백필 검증용 임시 공고",
                url="https://example.grib-test.kr/notice/sllm-doc-backfill-test",
            ).returning(notice.c.id)
        ).scalar_one()
        analysis_id = conn.execute(
            insert(analysis).values(
                notice_id=notice_id, source_kind="notice", input_ref="x", status="done", step="A1_extract", ver=1,
            ).returning(analysis.c.id)
        ).scalar_one()
        doc1_id = conn.execute(
            insert(analysis_doc).values(
                analysis_id=analysis_id, name="개인정보보호서약서.hwpx", kind="hwpx", bytes=10, sha256="a" * 64,
                extract_method="hwpx_xml", extract_ok=True, text="본인은 개인정보를 성실히 보호할 것을 서약합니다.",
            ).returning(analysis_doc.c.id)
        ).scalar_one()
        doc2_id = conn.execute(
            insert(analysis_doc).values(
                analysis_id=analysis_id, name="규격서.hwpx", kind="hwpx", bytes=20, sha256="b" * 64,
                extract_method="hwpx_xml", extract_ok=True, text="제3장 기술 규격\n초당 30프레임 이상 처리",
            ).returning(analysis_doc.c.id)
        ).scalar_one()
    yield notice_id, analysis_id, doc1_id, doc2_id
    with engine.begin() as conn:
        conn.execute(delete(analysis).where(analysis.c.id == analysis_id))  # cascade로 doc도 지움
        conn.execute(delete(notice).where(notice.c.id == notice_id))


def _classify_side_effect(doc1_id: int, doc2_id: int):
    def _fn(_text, *, trace_id: str):
        if trace_id == f"backfill_doc_{doc1_id}":
            return {"output": {"is_boilerplate": True, "reason": "서약서 양식"}}
        return {"output": {"is_boilerplate": False}}

    return _fn


def test_backfill_reclassifies_boilerplate_and_marks_checked(two_docs):
    _notice_id, analysis_id, doc1_id, doc2_id = two_docs
    with mock.patch(
        "app.services.analysis.sllm_doc_backfill.classify_doc",
        side_effect=_classify_side_effect(doc1_id, doc2_id),
    ):
        result = run_pending_sllm_doc_backfill(analysis_id, batch_limit=200)

    assert result == {"candidates": 2, "checked": 2, "reclassified": 1}

    with engine.connect() as conn:
        doc1 = conn.execute(
            select(analysis_doc.c.extract_ok, analysis_doc.c.text, analysis_doc.c.error, analysis_doc.c.sllm_checked_at)
            .where(analysis_doc.c.id == doc1_id)
        ).mappings().one()
        doc2 = conn.execute(
            select(analysis_doc.c.extract_ok, analysis_doc.c.text, analysis_doc.c.sllm_checked_at)
            .where(analysis_doc.c.id == doc2_id)
        ).mappings().one()

    assert doc1["extract_ok"] is False
    assert doc1["text"] is None
    assert "서약서 양식" in doc1["error"]
    assert doc1["sllm_checked_at"] is not None
    assert doc2["extract_ok"] is True
    assert doc2["text"] is not None
    assert doc2["sllm_checked_at"] is not None


def test_backfill_ignores_already_checked_docs(two_docs):
    _notice_id, analysis_id, doc1_id, doc2_id = two_docs
    with mock.patch(
        "app.services.analysis.sllm_doc_backfill.classify_doc",
        side_effect=_classify_side_effect(doc1_id, doc2_id),
    ):
        run_pending_sllm_doc_backfill(analysis_id, batch_limit=200)

    with mock.patch("app.services.analysis.sllm_doc_backfill.classify_doc") as mock_classify:
        result = run_pending_sllm_doc_backfill(analysis_id, batch_limit=200)

    assert result == {"candidates": 0, "checked": 0, "reclassified": 0}
    mock_classify.assert_not_called()


def test_backfill_marks_checked_and_continues_on_malformed_output(two_docs):
    _notice_id, analysis_id, doc1_id, doc2_id = two_docs

    def _fn(_text, *, trace_id: str):
        if trace_id == f"backfill_doc_{doc1_id}":
            raise SllmError("malformed_output", "분류 결과 형식이 올바르지 않습니다")
        return {"output": {"is_boilerplate": False}}

    with mock.patch("app.services.analysis.sllm_doc_backfill.classify_doc", side_effect=_fn):
        result = run_pending_sllm_doc_backfill(analysis_id, batch_limit=200)

    assert result == {"candidates": 2, "checked": 2, "reclassified": 0}
    with engine.connect() as conn:
        doc1 = conn.execute(
            select(analysis_doc.c.extract_ok, analysis_doc.c.sllm_checked_at).where(analysis_doc.c.id == doc1_id)
        ).mappings().one()
    assert doc1["extract_ok"] is True  # 판정 불능 — 원래 상태 유지
    assert doc1["sllm_checked_at"] is not None  # 그래도 확인 완료로 기록 — 다음 회차에 또 안 걸림


def test_backfill_stops_batch_without_marking_checked_on_connection_error(two_docs):
    _notice_id, analysis_id, doc1_id, _doc2_id = two_docs
    with mock.patch(
        "app.services.analysis.sllm_doc_backfill.classify_doc",
        side_effect=requests.exceptions.ConnectionError("connection refused"),
    ):
        result = run_pending_sllm_doc_backfill(analysis_id, batch_limit=200)

    assert result["checked"] == 0
    assert result["reclassified"] == 0
    with engine.connect() as conn:
        doc1 = conn.execute(select(analysis_doc.c.sllm_checked_at).where(analysis_doc.c.id == doc1_id)).scalar_one()
    assert doc1 is None  # 다음 회차에 재시도되도록 안 찍혀 있어야 함


def test_backfill_stops_batch_when_sllm_not_configured(two_docs):
    _notice_id, analysis_id, doc1_id, _doc2_id = two_docs
    with mock.patch(
        "app.services.analysis.sllm_doc_backfill.classify_doc",
        side_effect=SllmNotConfiguredError("설정 안 됨"),
    ):
        result = run_pending_sllm_doc_backfill(analysis_id, batch_limit=200)

    assert result["checked"] == 0
    with engine.connect() as conn:
        doc1 = conn.execute(select(analysis_doc.c.sllm_checked_at).where(analysis_doc.c.id == doc1_id)).scalar_one()
    assert doc1 is None


def test_backfill_returns_zero_counts_when_no_candidates():
    with engine.begin() as conn:
        source_id = _any_source_id(conn)
        temp_notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] sLLM 문서 백필 후보없음",
                url="https://example.grib-test.kr/notice/sllm-doc-backfill-empty",
            ).returning(notice.c.id)
        ).scalar_one()
        temp_analysis_id = conn.execute(
            insert(analysis).values(
                notice_id=temp_notice_id, source_kind="notice", input_ref="x", status="done", step="A1_extract", ver=1,
            ).returning(analysis.c.id)
        ).scalar_one()
    try:
        result = run_pending_sllm_doc_backfill(temp_analysis_id, batch_limit=200)
        assert result == {"candidates": 0, "checked": 0, "reclassified": 0}
    finally:
        with engine.begin() as conn:
            conn.execute(delete(analysis).where(analysis.c.id == temp_analysis_id))
            conn.execute(delete(notice).where(notice.c.id == temp_notice_id))
