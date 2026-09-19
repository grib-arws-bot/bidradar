"""사내 sLLM(C, classify-doc) 과거 데이터 백필 — app/services/analysis/sllm_doc_backfill.py 검증.
실제 sLLM 서버에 나가지 않는다 — classify_doc을 모킹해서 재분류·커서(after_id)·개별 실패
격리·미설정 시 즉시 중단만 확인한다.
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

import pytest
from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import analysis, analysis_doc, notice, source
from app.services.analysis.sllm_doc_backfill import backfill_doc_boilerplate_classification
from app.services.sllm_client import SllmError, SllmNotConfiguredError


def _any_source_id(conn) -> int:
    return conn.execute(select(source.c.id).limit(1)).scalar_one()


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


def test_backfill_reclassifies_boilerplate_and_keeps_real_doc(two_docs):
    _notice_id, analysis_id, doc1_id, doc2_id = two_docs
    with mock.patch(
        "app.services.analysis.sllm_doc_backfill.classify_doc",
        side_effect=_classify_side_effect(doc1_id, doc2_id),
    ):
        result = backfill_doc_boilerplate_classification(after_id=0, limit=200, analysis_id=analysis_id)

    assert result["checked"] == 2
    assert result["reclassified"] == 1
    assert result["last_id"] == doc2_id

    with engine.connect() as conn:
        doc1 = conn.execute(select(analysis_doc.c.extract_ok, analysis_doc.c.text, analysis_doc.c.error).where(analysis_doc.c.id == doc1_id)).mappings().one()
        doc2 = conn.execute(select(analysis_doc.c.extract_ok, analysis_doc.c.text).where(analysis_doc.c.id == doc2_id)).mappings().one()

    assert doc1["extract_ok"] is False
    assert doc1["text"] is None
    assert "서약서 양식" in doc1["error"]
    assert doc2["extract_ok"] is True
    assert doc2["text"] is not None


def test_backfill_respects_after_id_cursor(two_docs):
    _notice_id, analysis_id, doc1_id, doc2_id = two_docs
    with mock.patch(
        "app.services.analysis.sllm_doc_backfill.classify_doc",
        side_effect=_classify_side_effect(doc1_id, doc2_id),
    ) as mock_classify:
        result = backfill_doc_boilerplate_classification(after_id=doc1_id, limit=200, analysis_id=analysis_id)

    assert result["checked"] == 1  # doc1은 after_id로 제외됨
    assert result["last_id"] == doc2_id
    mock_classify.assert_called_once()


def test_backfill_skips_transient_sllm_error_and_continues(two_docs):
    _notice_id, analysis_id, doc1_id, doc2_id = two_docs

    def _fn(_text, *, trace_id: str):
        if trace_id == f"backfill_doc_{doc1_id}":
            raise SllmError("inference_failed", "모델 응답 없음")
        return {"output": {"is_boilerplate": False}}

    with mock.patch("app.services.analysis.sllm_doc_backfill.classify_doc", side_effect=_fn):
        result = backfill_doc_boilerplate_classification(after_id=0, limit=200, analysis_id=analysis_id)

    assert result["checked"] == 2  # 실패해도 건너뛰고 계속 진행
    assert result["reclassified"] == 0
    with engine.connect() as conn:
        doc1 = conn.execute(select(analysis_doc.c.extract_ok).where(analysis_doc.c.id == doc1_id)).scalar_one()
    assert doc1 is True  # 실패한 건 원래 상태 그대로


def test_backfill_raises_immediately_when_sllm_not_configured(two_docs):
    _notice_id, analysis_id, _doc1_id, _doc2_id = two_docs
    with mock.patch(
        "app.services.analysis.sllm_doc_backfill.classify_doc",
        side_effect=SllmNotConfiguredError("설정 안 됨"),
    ):
        with pytest.raises(SllmNotConfiguredError):
            backfill_doc_boilerplate_classification(after_id=0, limit=200, analysis_id=analysis_id)


def test_backfill_returns_zero_counts_when_no_candidates():
    result = backfill_doc_boilerplate_classification(after_id=2_000_000_000, limit=200)
    assert result == {"last_id": 2_000_000_000, "checked": 0, "reclassified": 0}
