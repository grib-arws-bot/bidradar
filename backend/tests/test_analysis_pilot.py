"""S8 A0+A1 파일럿(2026-09-03) — app/services/analysis_pilot.py 검증.

실제 iris.go.kr에 나가지 않는다 — url_guard.fetch를 모킹해서 발견(_discover_iris_attachments)·
DB 반영(analysis/analysis_doc)·중복실행 거부(S8 원칙 3)·미지원 소스 거부만 확인한다. 진짜
사이트 대조는 이번 기능을 만들 때 수동으로(id 320·321 실공고) 이미 검증했다.
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")
# app.config.settings는 프로세스당 한 번만 생성되는 싱글턴 — 이 파일이 pytest 수집 순서상
# 가장 먼저 app.db를 임포트하면 아래 두 값을 안 정해준 채로 실제 .env 값이 굳어버려서
# 이후 도는 다른 테스트 파일들의 로그인이 전부 401로 깨진다(2026-09-04 발견). 다른 테스트
# 파일과 동일한 값으로 고정해서 어떤 순서로 수집되든 같은 결과가 나오게 한다.
os.environ.setdefault("ADMIN_EMAIL", "report@grib.co.kr")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$argon2id$v=19$m=65536,t=3,p=4$9/7/Wg+VSkOsVCeiQiCz7w$bdDzJi9bKuERjBb6NHN0Ztk+X6uwxugL7kViHVRiqnY",
)

import pytest
from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import analysis, analysis_doc, notice, raw_payload, source
from app.services.analysis_pilot import (
    AnalysisInProgressError,
    UnsupportedSourceError,
    _discover_g2b_attachments,
    _discover_iris_attachments,
    get_latest_extraction,
    run_extraction_pilot,
)

_SAMPLE_HTML = """
<script>
f_bsnsAncm_downloadAtchFile('DOC1','FILE1','공고문.pdf' ,'12345');
f_bsnsAncm_downloadAtchFile('DOC1','FILE2','신청서 양식.zip' ,'99999');
f_bsnsAncm_downloadAtchFile('DOC1','FILE3','안내서.hwpx' ,'54321');
</script>
"""


def _fake_pdf_response():
    resp = mock.Mock()
    resp.content = b"%PDF-fake"
    return resp


def _fake_hwpx_response():
    import io
    import zipfile

    ns = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    xml = f'<?xml version="1.0"?><hs:sec xmlns:hs="ns" xmlns:hp="{ns}"><hp:p><hp:run><hp:t>안내서 본문</hp:t></hp:run></hp:p></hs:sec>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", xml)
    resp = mock.Mock()
    resp.content = buf.getvalue()
    return resp


def test_discover_iris_attachments_filters_zip_and_parses_tuples():
    found = _discover_iris_attachments(_SAMPLE_HTML)
    names = [f[0] for f in found]
    assert "공고문.pdf" in names
    assert "안내서.hwpx" in names
    assert "신청서 양식.zip" not in names  # zip은 발견 단계에서부터 제외


# ---- 나라장터 입찰공고정보서비스(2026-09-04) — 목록 API 응답에 첨부 URL이 이미 들어있어
# HTML 발견이 필요 없다. raw_payload에서 bidNtceNo로 항목을 다시 찾아 꺼낸다. ----------------

_G2B_SAMPLE_ITEM = {
    "bidNtceNo": "R26TEST9001",
    "bidNtceNm": "테스트 공고",
    "ntceSpecDocUrl1": "https://www.g2b.go.kr/download1",
    "ntceSpecFileNm1": "(붙임1) 공고문.hwp",
    "ntceSpecDocUrl2": "https://www.g2b.go.kr/download2",
    "ntceSpecFileNm2": "서식_신청서.zip",
    "ntceSpecDocUrl3": "",
    "ntceSpecFileNm3": "",
}


def test_discover_g2b_attachments_filters_zip_and_finds_by_bidntceno():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")).scalar_one()
        conn.execute(
            insert(raw_payload).values(source_id=source_id, endpoint="test", body={"items": [_G2B_SAMPLE_ITEM]})
        )
    try:
        with engine.connect() as conn:
            found = _discover_g2b_attachments(conn, source_id, "R26TEST9001")
        assert found == [("(붙임1) 공고문.hwp", "https://www.g2b.go.kr/download1")]
    finally:
        with engine.begin() as conn:
            conn.execute(delete(raw_payload).where(raw_payload.c.source_id == source_id, raw_payload.c.endpoint == "test"))


def test_discover_g2b_attachments_no_match_returns_empty():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")).scalar_one()
    with engine.connect() as conn:
        assert _discover_g2b_attachments(conn, source_id, "존재하지않는공고번호") == []


def test_discover_g2b_attachments_no_notice_no_returns_empty():
    # 발주계획현황서비스는 notice_no 자체를 안 매핑한다 — None이면 raw_payload를 뒤질 필요도 없음.
    with engine.connect() as conn:
        assert _discover_g2b_attachments(conn, source_id=1, notice_no=None) == []


@pytest.fixture
def iris_notice():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "IRIS 접수예정")).scalar_one()
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id,
                source_ver=1,
                stage="공모예고",
                title="[테스트] 파일럿 검증용 임시 공고",
                url="https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId=999999",
            ).returning(notice.c.id)
        ).scalar_one()
    yield notice_id
    with engine.begin() as conn:
        conn.execute(delete(analysis).where(analysis.c.notice_id == notice_id))  # cascade로 analysis_doc도 지움
        conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_run_extraction_pilot_end_to_end(iris_notice):
    with mock.patch("app.services.analysis_pilot.fetch") as mock_fetch:
        html_resp = mock.Mock()
        html_resp.text = _SAMPLE_HTML
        mock_fetch.side_effect = [html_resp, _fake_pdf_response(), _fake_hwpx_response()]

        with engine.begin() as conn:
            with mock.patch("app.services.document_extract.PdfReader") as MockReader:
                fake_page = mock.Mock()
                fake_page.extract_text.return_value = "공고문 본문 텍스트"
                MockReader.return_value.pages = [fake_page]
                result = run_extraction_pilot(conn, iris_notice)

    assert result["status"] == "done"
    assert result["attachments_found"] == 2  # zip 제외
    kinds = {d["kind"] for d in result["docs"]}
    assert kinds == {"pdf", "hwpx"}
    assert all(d["extract_ok"] for d in result["docs"])

    with engine.connect() as conn:
        latest = get_latest_extraction(conn, iris_notice)
    assert latest["status"] == "done"
    assert len(latest["docs"]) == 2
    assert any("공고문 본문" in (d["text"] or "") for d in latest["docs"])


@pytest.fixture
def g2b_notice():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")).scalar_one()
        conn.execute(insert(raw_payload).values(source_id=source_id, endpoint="test", body={"items": [_G2B_SAMPLE_ITEM]}))
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id,
                source_ver=1,
                stage="입찰공고",
                notice_no="R26TEST9001",
                title="[테스트] 나라장터 파일럿 검증용 임시 공고",
                url="https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26TEST9001&bidPbancOrd=000",
            ).returning(notice.c.id)
        ).scalar_one()
    yield notice_id
    with engine.begin() as conn:
        conn.execute(delete(analysis).where(analysis.c.notice_id == notice_id))
        conn.execute(delete(notice).where(notice.c.id == notice_id))
        conn.execute(delete(raw_payload).where(raw_payload.c.source_id == source_id, raw_payload.c.endpoint == "test"))


def test_run_extraction_pilot_g2b_end_to_end_uses_raw_payload_not_html(g2b_notice):
    # g2b 경로는 HTML을 아예 안 가져온다 — fetch가 첨부파일 다운로드 1번만 호출돼야 한다
    # (zip은 제외되므로 ntceSpecDocUrl1 하나뿐).
    with mock.patch("app.services.analysis_pilot.fetch") as mock_fetch:
        mock_fetch.return_value = _fake_pdf_response()  # 파일명은 hwp지만 내용 추출은 모킹
        with engine.begin() as conn:
            with mock.patch("app.services.document_extract._extract_hwp_full", return_value=None):
                with mock.patch("app.services.document_extract.olefile.OleFileIO") as MockOle:
                    MockOle.return_value.__enter__.return_value.exists.return_value = False
                    result = run_extraction_pilot(conn, g2b_notice)

    assert mock_fetch.call_count == 1  # HTML 발견 단계 없이 첨부파일 다운로드 1건만
    assert result["attachments_found"] == 1  # zip(서식_신청서.zip) 제외
    assert result["docs"][0]["name"] == "(붙임1) 공고문.hwp"


def test_run_extraction_pilot_rejects_duplicate_in_progress(iris_notice):
    with engine.begin() as conn:
        conn.execute(insert(analysis).values(notice_id=iris_notice, source_kind="notice", input_ref="x", status="running", ver=1))

    with engine.begin() as conn:
        with pytest.raises(AnalysisInProgressError):
            run_extraction_pilot(conn, iris_notice)


def test_run_extraction_pilot_rejects_non_iris_source():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "K-water 입찰공고")).scalar_one()
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id,
                source_ver=1,
                stage="입찰공고",
                title="[테스트] 비-IRIS 소스 거부 확인용",
                url="https://ebid.kwater.or.kr/fz?bidno=TEST",
            ).returning(notice.c.id)
        ).scalar_one()
        try:
            with pytest.raises(UnsupportedSourceError):
                run_extraction_pilot(conn, notice_id)
        finally:
            conn.execute(delete(notice).where(notice.c.id == notice_id))
