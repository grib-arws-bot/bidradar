"""app/services/pending_analysis.py 검증 — 첨부문서 자동 추출(A1)·AI 자동분석(A2)을
목록 수집(run_source)에서 분리한 후속 패스(2026-09-05, 의사결정_로그 56번).

공고 하나마다 별도 트랜잭션으로 처리되므로, run_source처럼 하나의 트랜잭션 안에서 목을
공유하지 않고 실제 커밋된 DB 상태를 각 단계마다 다시 조회해 확인한다.
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import analysis, notice, org, source, source_config, source_field_map
from app.services.pending_analysis import process_new_notices, run_pending_analysis


def _make_temp_source(conn, *, auto_extract: bool, auto_analyze: bool = False) -> int:
    src_id = conn.execute(
        insert(source)
        .values(
            name="테스트 소스(후속처리)", org_name="테스트기관", channel_name="테스트기관",
            base_url="https://example.grib-test.kr/api", stage="입찰공고", adapter_type="openapi",
            frequency_minutes=1440, is_system=False, skip_l1=True, active=True, legal_tier="A",
            auto_extract=auto_extract, auto_analyze=auto_analyze,
        )
        .returning(source.c.id)
    ).scalar_one()
    cfg_id = conn.execute(
        insert(source_config)
        .values(source_id=src_id, ver=1, config={"endpoint": "https://example.grib-test.kr/api", "items_path": "$.items[*]"})
        .returning(source_config.c.id)
    ).scalar_one()
    conn.execute(insert(source_field_map).values(source_config_id=cfg_id, target_field="title", source_path="$.title"))
    return src_id


def _make_notice(conn, source_id: int, url: str) -> int:
    org_id = conn.execute(insert(org).values(name="테스트발주기관_후속처리").returning(org.c.id)).scalar_one()
    return conn.execute(
        insert(notice).values(
            source_id=source_id, source_ver=1, stage="입찰공고", title="후속 처리 대상 공고",
            org_id=org_id, url=url,
        ).returning(notice.c.id)
    ).scalar_one()


def _cleanup(source_id: int, notice_ids: list[int]) -> None:
    with engine.begin() as conn:
        if notice_ids:
            conn.execute(delete(analysis).where(analysis.c.notice_id.in_(notice_ids)))
            conn.execute(delete(notice).where(notice.c.id.in_(notice_ids)))
        conn.execute(delete(org).where(org.c.name == "테스트발주기관_후속처리"))
        conn.execute(delete(source).where(source.c.id == source_id))


def test_run_pending_analysis_extracts_when_auto_extract_on(monkeypatch):
    html_response = mock.Mock()
    html_response.text = "<html>첨부파일 없음</html>"
    monkeypatch.setattr("app.services.analysis_pilot.fetch", mock.Mock(return_value=html_response))

    with engine.begin() as conn:
        source_id = _make_temp_source(conn, auto_extract=True)
        notice_id = _make_notice(conn, source_id, "https://www.iris.go.kr/test/TESTPENDING1")

    try:
        result = run_pending_analysis(source_id)
        assert result["extraction_candidates"] == 1
        assert result["auto_extracted"] == 1

        with engine.connect() as conn:
            status = conn.execute(select(analysis.c.status).where(analysis.c.notice_id == notice_id)).scalar_one()
        assert status == "done"
    finally:
        _cleanup(source_id, [notice_id])


def test_run_pending_analysis_skips_when_auto_extract_off():
    with engine.begin() as conn:
        source_id = _make_temp_source(conn, auto_extract=False)
        notice_id = _make_notice(conn, source_id, "https://www.iris.go.kr/test/TESTPENDING2")

    try:
        result = run_pending_analysis(source_id)
        assert result["extraction_candidates"] == 0
        assert result["auto_extracted"] == 0

        with engine.connect() as conn:
            has_analysis = conn.execute(select(analysis.c.id).where(analysis.c.notice_id == notice_id)).first()
        assert has_analysis is None
    finally:
        _cleanup(source_id, [notice_id])


def test_run_pending_analysis_does_not_retry_already_attempted_notice(monkeypatch):
    """한 번이라도 analysis 레코드가 생겼으면(성공이든 실패든) 다시 후보에 안 잡혀야 한다 —
    무한 재시도 방지."""
    pilot_fetch = mock.Mock()
    monkeypatch.setattr("app.services.analysis_pilot.fetch", pilot_fetch)

    with engine.begin() as conn:
        source_id = _make_temp_source(conn, auto_extract=True)
        notice_id = _make_notice(conn, source_id, "https://www.iris.go.kr/test/TESTPENDING3")
        conn.execute(
            insert(analysis).values(notice_id=notice_id, source_kind="notice", input_ref="x", status="failed", ver=1)
        )

    try:
        result = run_pending_analysis(source_id)
        assert result["extraction_candidates"] == 0
        pilot_fetch.assert_not_called()
    finally:
        _cleanup(source_id, [notice_id])


def test_run_pending_analysis_chains_structuring_when_auto_analyze_on(monkeypatch):
    # 첨부파일 하나가 있는 것처럼 꾸며야 A1이 실제로 문서 텍스트를 만들고, 그래야 이어지는
    # A2(run_structuring)가 "추출된 문서 텍스트가 없음" 오류 없이 진행된다. 실제 hwp/pdf 파싱은
    # 건너뛰고 extract_document 자체를 목으로 대체한다.
    from app.services.document_extract import ExtractResult

    html_with_attachment = (
        "<html>f_bsnsAncm_downloadAtchFile('DOC1','FILE1','붙임.hwpx','12345')</html>"
    )

    def _fetch_side_effect(url, *args, **kwargs):
        resp = mock.Mock()
        if "fileDownload" in url:
            resp.content = b"dummy-bytes"
        else:
            resp.text = html_with_attachment
        return resp

    monkeypatch.setattr("app.services.analysis_pilot.fetch", mock.Mock(side_effect=_fetch_side_effect))
    monkeypatch.setattr(
        "app.services.analysis_pilot.extract_document",
        mock.Mock(return_value=ExtractResult(ok=True, method="hwpx_xml", text="공고 원문 텍스트")),
    )

    anthropic_response = mock.Mock()
    anthropic_response.json.return_value = {
        "content": [{"type": "tool_use", "name": "extract_requirements", "input": {"requirements": [], "summary": {}}}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    monkeypatch.setattr("app.services.analysis.structure.fetch", mock.Mock(return_value=anthropic_response))

    from app.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")

    with engine.begin() as conn:
        source_id = _make_temp_source(conn, auto_extract=True, auto_analyze=True)
        notice_id = _make_notice(conn, source_id, "https://www.iris.go.kr/test/TESTPENDING4")

    try:
        result = run_pending_analysis(source_id)
        assert result["auto_extracted"] == 1
        assert result["analyze_candidates"] == 1
        assert result["auto_analyzed"] == 1

        with engine.connect() as conn:
            step = conn.execute(
                select(analysis.c.step).where(analysis.c.notice_id == notice_id).order_by(analysis.c.ver.desc())
            ).scalars().first()
        assert step == "A2_structure"
    finally:
        _cleanup(source_id, [notice_id])


# ---- process_new_notices(2026-09-07) — 방금 수집한 공고만 콕 집어 즉시 처리 ------------------


def test_process_new_notices_empty_list_short_circuits():
    result = process_new_notices(999999, [])
    assert result == {"extraction_candidates": 0, "auto_extracted": 0, "analyze_candidates": 0, "auto_analyzed": 0}


def test_process_new_notices_passes_prefetched_raw_item_through(monkeypatch):
    # 2026-09-08 — run_source가 방금 수집한 원본 API 항목을 넘겨주면, 그 notice_id에 대해
    # run_extraction_pilot이 목록 API를 다시 실시간 재조회하지 않도록 그대로 전달해야 한다.
    mock_extraction_pilot = mock.Mock(return_value={"analysis_id": 1, "status": "done", "attachments_found": 0, "docs": []})
    monkeypatch.setattr("app.services.pending_analysis.run_extraction_pilot", mock_extraction_pilot)

    with engine.begin() as conn:
        source_id = _make_temp_source(conn, auto_extract=True)
        notice_id = _make_notice(conn, source_id, "https://www.g2b.go.kr/test/TESTPREFETCH1")

    try:
        raw_item = {"bidNtceNo": "R26TESTPREFETCH1", "ntceSpecFileNm1": "공고문.hwp"}
        result = process_new_notices(source_id, [notice_id], raw_items_by_notice_id={notice_id: raw_item})
        assert result["auto_extracted"] == 1
        mock_extraction_pilot.assert_called_once()
        _, kwargs = mock_extraction_pilot.call_args
        assert kwargs["prefetched_raw_item"] is raw_item
    finally:
        _cleanup(source_id, [notice_id])


def test_process_new_notices_without_raw_items_map_passes_none(monkeypatch):
    # raw_items_by_notice_id를 아예 안 넘기면(예: 향후 다른 호출부) None이 전달돼야 한다 —
    # run_extraction_pilot 쪽에서 기존 방식(실시간 재조회)으로 자연히 폴백된다.
    mock_extraction_pilot = mock.Mock(return_value={"analysis_id": 1, "status": "done", "attachments_found": 0, "docs": []})
    monkeypatch.setattr("app.services.pending_analysis.run_extraction_pilot", mock_extraction_pilot)

    with engine.begin() as conn:
        source_id = _make_temp_source(conn, auto_extract=True)
        notice_id = _make_notice(conn, source_id, "https://www.g2b.go.kr/test/TESTPREFETCH2")

    try:
        process_new_notices(source_id, [notice_id])
        _, kwargs = mock_extraction_pilot.call_args
        assert kwargs["prefetched_raw_item"] is None
    finally:
        _cleanup(source_id, [notice_id])


def test_process_new_notices_extracts_when_auto_extract_on(monkeypatch):
    html_response = mock.Mock()
    html_response.text = "<html>첨부파일 없음</html>"
    monkeypatch.setattr("app.services.analysis_pilot.fetch", mock.Mock(return_value=html_response))

    with engine.begin() as conn:
        source_id = _make_temp_source(conn, auto_extract=True)
        notice_id = _make_notice(conn, source_id, "https://www.iris.go.kr/test/TESTNEWNOTICE1")

    try:
        result = process_new_notices(source_id, [notice_id])
        assert result["extraction_candidates"] == 1
        assert result["auto_extracted"] == 1

        with engine.connect() as conn:
            status = conn.execute(select(analysis.c.status).where(analysis.c.notice_id == notice_id)).scalar_one()
        assert status == "done"
    finally:
        _cleanup(source_id, [notice_id])


def test_process_new_notices_skips_when_auto_extract_off():
    with engine.begin() as conn:
        source_id = _make_temp_source(conn, auto_extract=False)
        notice_id = _make_notice(conn, source_id, "https://www.iris.go.kr/test/TESTNEWNOTICE2")

    try:
        result = process_new_notices(source_id, [notice_id])
        assert result["extraction_candidates"] == 0
        assert result["auto_extracted"] == 0
    finally:
        _cleanup(source_id, [notice_id])


def test_process_new_notices_ignores_unrelated_backlog(monkeypatch):
    """이 소스에 첨부분석을 아직 안 한 오래된 공고(backlog_notice_id)가 있어도, notice_ids로
    지정하지 않으면 손대지 않는다 — process_new_notices는 지정한 공고만 대상으로 한다는
    핵심 동작(2026-09-07 실측 발견 버그의 수정 사항)."""
    html_response = mock.Mock()
    html_response.text = "<html>첨부파일 없음</html>"
    monkeypatch.setattr("app.services.analysis_pilot.fetch", mock.Mock(return_value=html_response))

    with engine.begin() as conn:
        source_id = _make_temp_source(conn, auto_extract=True)
        backlog_notice_id = _make_notice(conn, source_id, "https://www.iris.go.kr/test/TESTBACKLOG1")
        new_notice_id = _make_notice(conn, source_id, "https://www.iris.go.kr/test/TESTNEWNOTICE3")

    try:
        result = process_new_notices(source_id, [new_notice_id])
        assert result["extraction_candidates"] == 1
        assert result["auto_extracted"] == 1

        with engine.connect() as conn:
            backlog_has_analysis = conn.execute(
                select(analysis.c.id).where(analysis.c.notice_id == backlog_notice_id)
            ).first()
            new_status = conn.execute(
                select(analysis.c.status).where(analysis.c.notice_id == new_notice_id)
            ).scalar_one()
        assert backlog_has_analysis is None  # 잔고는 건드리지 않음
        assert new_status == "done"
    finally:
        _cleanup(source_id, [backlog_notice_id, new_notice_id])


def test_process_new_notices_chains_structuring_when_auto_analyze_on(monkeypatch):
    from app.services.document_extract import ExtractResult

    html_with_attachment = (
        "<html>f_bsnsAncm_downloadAtchFile('DOC1','FILE1','붙임.hwpx','12345')</html>"
    )

    def _fetch_side_effect(url, *args, **kwargs):
        resp = mock.Mock()
        if "fileDownload" in url:
            resp.content = b"dummy-bytes"
        else:
            resp.text = html_with_attachment
        return resp

    monkeypatch.setattr("app.services.analysis_pilot.fetch", mock.Mock(side_effect=_fetch_side_effect))
    monkeypatch.setattr(
        "app.services.analysis_pilot.extract_document",
        mock.Mock(return_value=ExtractResult(ok=True, method="hwpx_xml", text="공고 원문 텍스트")),
    )

    anthropic_response = mock.Mock()
    anthropic_response.json.return_value = {
        "content": [{"type": "tool_use", "name": "extract_requirements", "input": {"requirements": [], "summary": {}}}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    monkeypatch.setattr("app.services.analysis.structure.fetch", mock.Mock(return_value=anthropic_response))

    from app.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")

    with engine.begin() as conn:
        source_id = _make_temp_source(conn, auto_extract=True, auto_analyze=True)
        notice_id = _make_notice(conn, source_id, "https://www.iris.go.kr/test/TESTNEWNOTICE4")

    try:
        result = process_new_notices(source_id, [notice_id])
        assert result["auto_extracted"] == 1
        assert result["analyze_candidates"] == 1
        assert result["auto_analyzed"] == 1

        with engine.connect() as conn:
            step = conn.execute(
                select(analysis.c.step).where(analysis.c.notice_id == notice_id).order_by(analysis.c.ver.desc())
            ).scalars().first()
        assert step == "A2_structure"
    finally:
        _cleanup(source_id, [notice_id])


def test_process_new_notices_records_a2_failure_instead_of_losing_it(monkeypatch):
    """2026-09-08 실측 버그 회귀 테스트 — A2(LLM 호출)가 실패하면 그 실패가 DB에 남아야
    한다("시도조차 안 한 것"처럼 조용히 사라지면 안 됨, CLAUDE.md S8). 원인은
    process_new_notices가 run_structuring_for_notice를 try/except **밖에서** 감싼 with
    engine.begin()으로 부르고 있었던 것 — 실패 시 그 트랜잭션 전체가 롤백돼 방금 conn에
    기록한 'failed' 상태까지 같이 사라졌다(IRIS 접수예정 자동수집 중 실제로 발생)."""
    from app.services.document_extract import ExtractResult

    html_with_attachment = "<html>f_bsnsAncm_downloadAtchFile('DOC1','FILE1','붙임.hwpx','12345')</html>"

    def _fetch_side_effect(url, *args, **kwargs):
        resp = mock.Mock()
        if "fileDownload" in url:
            resp.content = b"dummy-bytes"
        else:
            resp.text = html_with_attachment
        return resp

    monkeypatch.setattr("app.services.analysis_pilot.fetch", mock.Mock(side_effect=_fetch_side_effect))
    monkeypatch.setattr(
        "app.services.analysis_pilot.extract_document",
        mock.Mock(return_value=ExtractResult(ok=True, method="hwpx_xml", text="공고 원문 텍스트")),
    )
    # A2의 LLM 호출 자체가 실패하는 상황(네트워크 오류 등)을 재현.
    monkeypatch.setattr(
        "app.services.analysis.structure.fetch", mock.Mock(side_effect=RuntimeError("일시적 네트워크 오류")),
    )
    from app.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")

    with engine.begin() as conn:
        source_id = _make_temp_source(conn, auto_extract=True, auto_analyze=True)
        notice_id = _make_notice(conn, source_id, "https://www.iris.go.kr/test/TESTA2FAILURE")

    try:
        result = process_new_notices(source_id, [notice_id])
        assert result["auto_extracted"] == 1
        assert result["analyze_candidates"] == 1
        assert result["auto_analyzed"] == 0  # 실패했으니 성공 카운트엔 안 들어감

        with engine.connect() as conn:
            row = conn.execute(
                select(analysis.c.step, analysis.c.status, analysis.c.verdict)
                .where(analysis.c.notice_id == notice_id)
                .order_by(analysis.c.ver.desc())
            ).first()
        # 핵심 검증: "시도 안 함"(A1_extract/done)이 아니라 실제로 실패 기록이 남아야 한다.
        assert row.step == "A2_structure"
        assert row.status == "failed"
        assert row.verdict is not None and "일시적 네트워크 오류" in row.verdict
    finally:
        _cleanup(source_id, [notice_id])
