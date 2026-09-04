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
from app.models import analysis, analysis_doc, notice, source
from app.services.analysis_pilot import (
    AnalysisInProgressError,
    UnsupportedSourceError,
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
    names = [f[2] for f in found]
    assert "공고문.pdf" in names
    assert "안내서.hwpx" in names
    assert "신청서 양식.zip" not in names  # zip은 발견 단계에서부터 제외


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
