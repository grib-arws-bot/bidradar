"""app/services/reprocess_attachments.py 검증 — 이미 A1을 시도했지만 첨부 0건으로 남은
g2b 계열 공고를 캐시된 raw_payload로 재처리(2026-09-08, 발주계획/사전규격 일괄재처리).

apis.data.go.kr을 전혀 호출하지 않는다는 게 핵심 계약이므로, 모든 테스트에서
fetch_openapi_items가 절대 호출되지 않음을 확인한다.

실제 소스(125/176)를 재사용하지 않고 매번 격리된 임시 소스를 만든다 — 실제 소스로 이
서비스를 시험하다가 실사용 raw_payload 캐시를 삭제해버린 사고가 있었다(2026-09-08).
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

import pytest
from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import analysis, analysis_doc, notice, org, raw_payload, source, source_config
from app.services.document_extract import ExtractResult
from app.services.reprocess_attachments import reprocess_empty_extractions

_PRESTANDARD_ITEM = {
    "bfSpecRgstNo": "R26TESTRP001",
    "specDocFileUrl1": "https://www.g2b.go.kr/pn/pnz/pnza/UntyAtchFile/downloadFile.do?bfSpecRegNo=R26TESTRP001&fileType=BFDTL&fileSeq=1",
}


def _make_temp_prestandard_source(conn) -> int:
    src_id = conn.execute(
        insert(source)
        .values(
            name="테스트 소스(재처리)", org_name="테스트기관", channel_name="테스트기관",
            base_url="https://apis.data.go.kr/test/HrcspSsstndrdInfoService/testOp", stage="사전규격",
            adapter_type="openapi", frequency_minutes=1440, is_system=False, skip_l1=True, active=True,
            legal_tier="A", auto_extract=True, auto_analyze=False,
        )
        .returning(source.c.id)
    ).scalar_one()
    conn.execute(
        insert(source_config).values(
            source_id=src_id, ver=1,
            config={"endpoint": "https://apis.data.go.kr/test/HrcspSsstndrdInfoService/testOp"},
        )
    )
    return src_id


def _make_empty_analysis_notice(conn, source_id: int, notice_no: str, url: str) -> tuple[int, int]:
    """"A1 시도완료·첨부 0건" 상태로 이미 기록된 공고 하나를 만든다."""
    org_id = conn.execute(insert(org).values(name=f"테스트발주기관_재처리_{notice_no}").returning(org.c.id)).scalar_one()
    notice_id = conn.execute(
        insert(notice).values(
            source_id=source_id, source_ver=1, stage="사전규격", notice_no=notice_no,
            title="[테스트] 재처리 검증용 공고", org_id=org_id, url=url,
        ).returning(notice.c.id)
    ).scalar_one()
    analysis_id = conn.execute(
        insert(analysis).values(
            notice_id=notice_id, source_kind="notice", input_ref=url, status="done",
            step="A1_extract", ver=1,
        ).returning(analysis.c.id)
    ).scalar_one()
    return notice_id, analysis_id


@pytest.fixture
def prestandard_source():
    with engine.begin() as conn:
        source_id = _make_temp_prestandard_source(conn)
    yield source_id
    with engine.begin() as conn:
        notice_ids = conn.execute(select(notice.c.id).where(notice.c.source_id == source_id)).scalars().all()
        if notice_ids:
            conn.execute(delete(analysis_doc).where(analysis_doc.c.analysis_id.in_(
                select(analysis.c.id).where(analysis.c.notice_id.in_(notice_ids))
            )))
            conn.execute(delete(analysis).where(analysis.c.notice_id.in_(notice_ids)))
            conn.execute(delete(notice).where(notice.c.id.in_(notice_ids)))
        conn.execute(delete(org).where(org.c.name.like("테스트발주기관_재처리_%")))
        conn.execute(delete(raw_payload).where(raw_payload.c.source_id == source_id))
        conn.execute(delete(source_config).where(source_config.c.source_id == source_id))
        conn.execute(delete(source).where(source.c.id == source_id))


def test_reprocess_finds_docs_from_cached_raw_payload_without_live_api(prestandard_source):
    source_id = prestandard_source
    with engine.begin() as conn:
        notice_id, _ = _make_empty_analysis_notice(
            conn, source_id, "R26TESTRP001",
            "https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26TESTRP001",
        )
        conn.execute(insert(raw_payload).values(source_id=source_id, endpoint="test", body={"items": [_PRESTANDARD_ITEM]}))

    fake_response = mock.Mock()
    fake_response.content = b"%PDF-1.4 fake content"
    fake_response.headers = {}  # 실제 Response.headers처럼 dict-like — Content-Disposition 없음

    with mock.patch("app.services.g2b_attachments.fetch_openapi_items") as mock_fetch_items:
        with mock.patch("app.services.analysis_pilot.fetch", return_value=fake_response):
            with mock.patch(
                "app.services.analysis_pilot.extract_document",
                return_value=ExtractResult(text="추출된 본문", method="pdf_text", ok=True, error=None),
            ):
                result = reprocess_empty_extractions(source_id)

    mock_fetch_items.assert_not_called()  # 라이브 재조회 금지가 핵심 계약
    assert result["candidates"] == 1
    assert result["no_cache_match"] == 0
    assert result["reprocessed"] == 1
    assert result["found_docs"] == 1

    with engine.connect() as conn:
        docs = conn.execute(
            select(analysis_doc.c.extract_ok).where(
                analysis_doc.c.analysis_id.in_(
                    select(analysis.c.id).where(analysis.c.notice_id == notice_id, analysis.c.ver == 2)
                )
            )
        ).scalars().all()
    assert docs == [True]


def test_reprocess_skips_when_no_cache_match(prestandard_source):
    source_id = prestandard_source
    with engine.begin() as conn:
        _make_empty_analysis_notice(
            conn, source_id, "R26TESTRP002",
            "https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26TESTRP002",
        )
        # raw_payload를 아예 안 남김 — 캐시에서 못 찾는 상황

    with mock.patch("app.services.g2b_attachments.fetch_openapi_items") as mock_fetch_items:
        result = reprocess_empty_extractions(source_id)

    mock_fetch_items.assert_not_called()
    assert result["candidates"] == 1
    assert result["no_cache_match"] == 1
    assert result["reprocessed"] == 0
    assert result["found_docs"] == 0


def test_reprocess_ignores_notices_with_existing_successful_doc(prestandard_source):
    source_id = prestandard_source
    with engine.begin() as conn:
        _notice_id, analysis_id = _make_empty_analysis_notice(
            conn, source_id, "R26TESTRP003",
            "https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26TESTRP003",
        )
        conn.execute(
            insert(analysis_doc).values(
                analysis_id=analysis_id, name="이미성공.pdf", kind="pdf", bytes=10, sha256="x",
                extract_ok=True, text="이미 성공한 첨부",
            )
        )

    with mock.patch("app.services.g2b_attachments.fetch_openapi_items") as mock_fetch_items:
        result = reprocess_empty_extractions(source_id)

    mock_fetch_items.assert_not_called()
    assert result["candidates"] == 0
    assert result["reprocessed"] == 0
