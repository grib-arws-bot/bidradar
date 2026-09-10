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
from app.models import interest_topic, keyword_rule, notice_score
from app.services.analysis_pilot import (
    AnalysisInProgressError,
    UnsupportedSourceError,
    L2_ATTACHMENT_PROMOTE_THRESHOLD,
    _classify_from_attachments,
    _decode_zip_name,
    _discover_iris_attachments,
    _filename_from_content_disposition,
    get_latest_extraction,
    run_extraction_pilot,
)
from app.services.g2b_attachments import _should_skip_by_name

_SAMPLE_HTML = """
<script>
f_bsnsAncm_downloadAtchFile('DOC1','FILE1','공고문.pdf' ,'12345');
f_bsnsAncm_downloadAtchFile('DOC1','FILE2','신청서 양식.zip' ,'99999');
f_bsnsAncm_downloadAtchFile('DOC1','FILE3','안내서.hwpx' ,'54321');
f_bsnsAncm_downloadAtchFile('DOC1','FILE4','제안요청서(RFP) 등 관련서식.zip' ,'11111');
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


def _fake_zip_response(files: dict[str, bytes]):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    resp = mock.Mock()
    resp.content = buf.getvalue()
    return resp


def test_decode_zip_name_recovers_cp949_korean_filename():
    # 2026-09-07 발견 — Windows에서 만든 zip은 내부 파일명을 CP949로 인코딩하면서도 UTF-8
    # 플래그는 안 세워두는 경우가 흔하다. zipfile은 그 경우 항상 CP437로 디코딩해버려 한글이
    # 깨진다(사용자가 실제 화면 스크린샷으로 제보).
    import zipfile

    original = "테스트문서.hwp"
    mis_decoded = original.encode("cp949").decode("cp437")
    info = zipfile.ZipInfo(filename=mis_decoded)
    info.flag_bits = 0  # UTF-8 플래그 없음
    assert _decode_zip_name(info) == original


def test_decode_zip_name_leaves_utf8_flagged_name_alone():
    import zipfile

    info = zipfile.ZipInfo(filename="정상파일.hwp")
    info.flag_bits = 0x800  # UTF-8 플래그 있음 — zipfile이 이미 올바르게 디코딩했다고 신뢰
    assert _decode_zip_name(info) == "정상파일.hwp"


def test_filename_from_content_disposition_recovers_real_name_with_extension():
    # 2026-09-09 실측 — 사전규격정보서비스는 specDocFileUrl에 파일명 파라미터가 없어(오늘
    # 실제 배치 325건 전부 확인) 확장자 없는 "규격서1" 같은 대체 이름을 쓰는데, 그러면
    # _kind_from_filename이 "other"로 판정해 지원 형식이 있는 파일도 무조건 추출 실패한다.
    # 실제 다운로드 응답엔 Content-Disposition에 진짜 파일명(확장자 포함)이 있다.
    headers = {"Content-Disposition": "attachment;filename=%EA%B3%BC%EC%97%85%EC%A7%80%EC%8B%9C%EC%84%9C.hwpx;"}
    assert _filename_from_content_disposition(headers, fallback="규격서1") == "과업지시서.hwpx"


def test_filename_from_content_disposition_falls_back_when_header_missing():
    assert _filename_from_content_disposition({}, fallback="규격서1") == "규격서1"


def test_should_skip_by_name_matches_routine_document_keywords():
    assert _should_skip_by_name("신청서 양식.hwp") is True
    assert _should_skip_by_name("연구시설장비비 통합관리제 매뉴얼.pdf") is True
    assert _should_skip_by_name("2026년도 로봇산업기술개발사업 공고문.hwpx") is False


def test_should_skip_by_name_ignores_whitespace_inside_keyword():
    # 실측(2026-09-05, 로봇산업기술개발사업 공고): "붙임 03. 관련 법령 및 규정.zip"처럼 키워드
    # 중간에 띄어쓰기가 들어간 실제 파일명이 있다 — 그대로 부분일치하면 놓친다.
    assert _should_skip_by_name("붙임 03. 관련 법령 및 규정.zip") is True


def test_discover_iris_attachments_filters_by_name_keyword_not_zip():
    found = _discover_iris_attachments(_SAMPLE_HTML)
    names = [f["name"] for f in found]
    assert "공고문.pdf" in names
    assert "안내서.hwpx" in names
    assert "신청서 양식.zip" not in names  # "양식" 키워드로 제외 — zip이라서가 아님
    assert "제안요청서(RFP) 등 관련서식.zip" in names  # zip이라도 이름이 안 걸리면 발견됨(2026-09-05)


# g2b 계열 첨부 발견 단위테스트(_discover_g2b_attachments·_g2b_*_attachments)는
# tests/test_g2b_attachments.py로 이동(2026-09-08, app/services/g2b_attachments.py 분리와
# 함께). 아래는 이 파일에 남는 end-to-end(run_extraction_pilot 전체 파이프라인) 테스트가
# 쓰는 샘플 아이템이다.

_G2B_SAMPLE_ITEM = {
    "bidNtceNo": "R26TEST9001",
    "bidNtceNm": "테스트 공고",
    "ntceSpecDocUrl1": "https://www.g2b.go.kr/download1",
    "ntceSpecFileNm1": "(붙임1) 공고문.hwp",
    "ntceSpecDocUrl2": "https://www.g2b.go.kr/download2",
    "ntceSpecFileNm2": "신청서_양식.zip",
    "ntceSpecDocUrl3": "",
    "ntceSpecFileNm3": "",
}

_G2B_ORDERPLAN_SAMPLE_ITEM = {
    "orderPlanUntyNo": "R26TEST7001",
    "specCntnts": "스마트제조 장비 IoT 연계 모니터링 운영 용역 — 규격 개요",
    "specItemNm1": "모니터링 대상",
    "specItemCntnts1": "소상공인 스마트공장 설비 500개소",
    "specItemNm2": "",
    "specItemCntnts2": "",
}

# 2026-09-09 실측 — 사전규격정보서비스는 specDocFileUrl에 파일명 파라미터가 없다(오늘 실제
# 배치 325건 전부 확인). fileNm 쿼리파라미터가 없는 이 상황을 그대로 재현한다.
_G2B_PRESTANDARD_NO_FILENAME_ITEM = {
    "bfSpecRgstNo": "R26TEST8002",
    "specDocFileUrl1": "https://www.g2b.go.kr/pn/pnz/pnza/UntyAtchFile/downloadFile.do?bfSpecRegNo=R26TEST8002&fileType=BFDTL&fileSeq=1",
}


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
        zip_resp = _fake_zip_response({"관련서식.pdf": b"%PDF-fake"})  # zip도 이제 열어서 분석
        mock_fetch.side_effect = [html_resp, _fake_pdf_response(), _fake_hwpx_response(), zip_resp]

        with engine.begin() as conn:
            with mock.patch("app.services.document_extract.PdfReader") as MockReader:
                fake_page = mock.Mock()
                fake_page.extract_text.return_value = "공고문 본문 텍스트"
                MockReader.return_value.pages = [fake_page]
                result = run_extraction_pilot(conn, iris_notice)

    assert result["status"] == "done"
    assert result["attachments_found"] == 3  # pdf·hwpx·zip(관련서식) — zip도 이름이 안 걸리면 포함
    kinds = {d["kind"] for d in result["docs"]}
    assert kinds == {"pdf", "hwpx"}  # zip 안의 파일도 확장자 기준으로 pdf로 분류됨
    assert all(d["extract_ok"] for d in result["docs"])

    with engine.connect() as conn:
        latest = get_latest_extraction(conn, iris_notice)
    assert latest["status"] == "done"
    assert len(latest["docs"]) == 3  # zip 안의 관련서식.pdf까지 별도 행으로
    assert any("공고문 본문" in (d["text"] or "") for d in latest["docs"])


@pytest.fixture
def g2b_notice():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")).scalar_one()
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


def test_run_extraction_pilot_g2b_end_to_end_uses_live_api_not_html(g2b_notice):
    # g2b 경로는 HTML을 아예 안 가져온다 — fetch가 첨부파일 다운로드 1번만 호출돼야 한다
    # ("신청서_양식.zip"은 이름 키워드로 발견 단계에서부터 제외되므로 나머지 1건뿐). 목록
    # API 재조회(2026-09-06)는 raw_payload 캐시가 아니라 fetch_openapi_items를 모킹한다.
    with mock.patch("app.services.g2b_attachments.fetch_openapi_items", return_value=[_G2B_SAMPLE_ITEM]):
        with mock.patch("app.services.analysis_pilot.fetch") as mock_fetch:
            mock_fetch.return_value = _fake_pdf_response()  # 파일명은 hwp지만 내용 추출은 모킹
            with engine.begin() as conn:
                with mock.patch("app.services.document_extract._extract_hwp_full", return_value=None):
                    with mock.patch("app.services.document_extract.olefile.OleFileIO") as MockOle:
                        MockOle.return_value.__enter__.return_value.exists.return_value = False
                        result = run_extraction_pilot(conn, g2b_notice)

    assert mock_fetch.call_count == 1  # HTML 발견 단계 없이 첨부파일 다운로드 1건만
    assert result["attachments_found"] == 1  # 신청서_양식.zip은 이름으로 제외됨
    assert result["docs"][0]["name"] == "(붙임1) 공고문.hwp"


def test_run_extraction_pilot_with_prefetched_item_skips_live_relookup(g2b_notice):
    # 2026-09-08 — 방금 수집한 공고는 원본 API 항목을 이미 갖고 있으므로 목록 API를 다시
    # 실시간 재조회하면 안 된다(느리고, apis.data.go.kr 불안정 시 조용한 실패로 이어짐,
    # 사용자가 실제 사전규격 223건 수집으로 확인). fetch_openapi_items가 아예 안 불려야 한다.
    with mock.patch("app.services.g2b_attachments.fetch_openapi_items") as mock_fetch_items:
        with mock.patch("app.services.analysis_pilot.fetch") as mock_fetch:
            mock_fetch.return_value = _fake_pdf_response()
            with engine.begin() as conn:
                with mock.patch("app.services.document_extract._extract_hwp_full", return_value=None):
                    with mock.patch("app.services.document_extract.olefile.OleFileIO") as MockOle:
                        MockOle.return_value.__enter__.return_value.exists.return_value = False
                        result = run_extraction_pilot(conn, g2b_notice, prefetched_raw_item=_G2B_SAMPLE_ITEM)

    mock_fetch_items.assert_not_called()  # 목록 API 재조회가 아예 없어야 함
    assert result["attachments_found"] == 1
    assert result["docs"][0]["name"] == "(붙임1) 공고문.hwp"


# ---- zip 첨부는 안의 모든 파일을 개별 분석(2026-09-05) ------------------------------------


_G2B_ZIP_SAMPLE_ITEM = {
    "bidNtceNo": "R26TEST9002",
    "bidNtceNm": "테스트 공고(zip)",
    "ntceSpecDocUrl1": "https://www.g2b.go.kr/download-zip",
    "ntceSpecFileNm1": "제안요청서(RFP) 등 관련서식.zip",
}


@pytest.fixture
def g2b_zip_notice():
    """zip 첨부 하나(이름은 안 걸림) 안에 스킵 대상 1개 + 분석 대상 1개가 든 상황."""
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")).scalar_one()
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", notice_no="R26TEST9002",
                title="[테스트] zip 첨부 검증용 임시 공고",
                url="https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26TEST9002&bidPbancOrd=000",
            ).returning(notice.c.id)
        ).scalar_one()
    yield notice_id
    with engine.begin() as conn:
        conn.execute(delete(analysis).where(analysis.c.notice_id == notice_id))
        conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_run_extraction_pilot_expands_zip_and_skips_routine_files_inside(g2b_zip_notice):
    zip_response = _fake_zip_response({
        "매뉴얼.hwp": b"ignored",  # 이름 키워드로 제외돼야 함(내부 파일에도 필터 적용)
        "제안요청서.pdf": b"%PDF-fake",
    })
    with mock.patch("app.services.g2b_attachments.fetch_openapi_items", return_value=[_G2B_ZIP_SAMPLE_ITEM]):
        with mock.patch("app.services.analysis_pilot.fetch", return_value=zip_response):
            with engine.begin() as conn:
                with mock.patch("app.services.document_extract.PdfReader") as MockReader:
                    fake_page = mock.Mock()
                    fake_page.extract_text.return_value = "제안요청서 본문"
                    MockReader.return_value.pages = [fake_page]
                    result = run_extraction_pilot(conn, g2b_zip_notice)

    assert result["status"] == "done"
    names = [d["name"] for d in result["docs"]]
    assert names == ["제안요청서(RFP) 등 관련서식.zip :: 제안요청서.pdf"]  # 매뉴얼.hwp는 안 나옴
    assert result["docs"][0]["extract_ok"] is True
    assert result["docs"][0]["kind"] == "pdf"


@pytest.fixture
def g2b_orderplan_notice():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "나라장터 발주계획현황서비스(용역)")).scalar_one()
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id,
                source_ver=1,
                stage="발주계획",
                title="[테스트] 발주계획 인라인 텍스트 검증용 임시 공고",
                url="https://www.g2b.go.kr/link/PRPA015_01/single/?oderPlanNo=R26TEST7001",
                extra={"orderPlanUntyNo": "R26TEST7001"},
            ).returning(notice.c.id)
        ).scalar_one()
    yield notice_id
    with engine.begin() as conn:
        conn.execute(delete(analysis).where(analysis.c.notice_id == notice_id))
        conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_run_extraction_pilot_orderplan_end_to_end_skips_download_uses_inline_text(g2b_orderplan_notice):
    # 발주계획은 다운로드할 파일이 없다 — fetch()(url_guard, 파일 다운로드용)는 한 번도
    # 호출되면 안 되고, API가 준 텍스트가 그대로 analysis_doc.text에 남아야 한다.
    with mock.patch("app.services.g2b_attachments.fetch_openapi_items", return_value=[_G2B_ORDERPLAN_SAMPLE_ITEM]):
        with mock.patch("app.services.analysis_pilot.fetch") as mock_fetch:
            with engine.begin() as conn:
                result = run_extraction_pilot(conn, g2b_orderplan_notice)

    mock_fetch.assert_not_called()
    assert result["status"] == "done"
    assert result["attachments_found"] == 2
    assert {d["name"] for d in result["docs"]} == {"규격내용", "모니터링 대상"}
    assert all(d["kind"] == "text" and d["extract_method"] == "api_inline_text" for d in result["docs"])
    assert all(d["extract_ok"] for d in result["docs"])


@pytest.fixture
def g2b_prestandard_notice():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "나라장터 사전규격정보서비스(용역)")).scalar_one()
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="사전규격", notice_no="R26TEST8002",
                title="[테스트] 사전규격 파일명 보완 검증용 임시 공고",
                url="https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26TEST8002",
            ).returning(notice.c.id)
        ).scalar_one()
    yield notice_id
    with engine.begin() as conn:
        conn.execute(delete(analysis).where(analysis.c.notice_id == notice_id))
        conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_run_extraction_pilot_recovers_filename_from_content_disposition(g2b_prestandard_notice):
    # 2026-09-09 회귀 테스트 — 사전규격 응답 URL에 파일명이 없어 "규격서1"(확장자 없음)로
    # 대체되면, 실제 다운로드 응답의 Content-Disposition에서 진짜 파일명(확장자 포함)을
    # 복구해 지원 형식으로 정상 추출돼야 한다. 이걸 못 고치면 사전규격 첨부는 100% 실패한다
    # (오늘 실제 배치 205건에서 재현됨).
    fake_response = mock.Mock()
    fake_response.content = b"%PDF-fake"
    fake_response.headers = {"Content-Disposition": "attachment;filename=%EA%B7%9C%EA%B2%A9%EC%84%9C.pdf;"}

    with mock.patch("app.services.g2b_attachments.fetch_openapi_items", return_value=[_G2B_PRESTANDARD_NO_FILENAME_ITEM]):
        with mock.patch("app.services.analysis_pilot.fetch", return_value=fake_response):
            with engine.begin() as conn:
                with mock.patch("app.services.document_extract.PdfReader") as MockReader:
                    fake_page = mock.Mock()
                    fake_page.extract_text.return_value = "규격서 본문"
                    MockReader.return_value.pages = [fake_page]
                    result = run_extraction_pilot(conn, g2b_prestandard_notice)

    assert result["status"] == "done"
    assert result["docs"][0]["name"] == "규격서.pdf"  # "규격서1"이 아니라 진짜 파일명으로 대체됨
    assert result["docs"][0]["kind"] == "pdf"
    assert result["docs"][0]["extract_ok"] is True


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


# ---- 첨부문서 원문으로도 관심주제(L2) 채점(2026-09-07) ----------------------------------


@pytest.fixture
def attachment_classify_topic():
    """제목이 아니라 본문에서만 매칭되는 걸 확인해야 하므로 실제 시드 키워드와 안 겹치는
    전용 임시 주제·키워드를 쓴다."""
    with engine.begin() as conn:
        topic_id = conn.execute(
            insert(interest_topic).values(name="[테스트] 첨부분류용 주제", sort_order=9999).returning(interest_topic.c.id)
        ).scalar_one()
        conn.execute(insert(keyword_rule).values(interest_topic_id=topic_id, term="스마트팩토리", weight_class="core", weight=4))
        conn.execute(insert(keyword_rule).values(interest_topic_id=topic_id, term="약한신호", weight_class="ctx", weight=1))
    yield topic_id
    with engine.begin() as conn:
        conn.execute(delete(keyword_rule).where(keyword_rule.c.interest_topic_id == topic_id))
        conn.execute(delete(interest_topic).where(interest_topic.c.id == topic_id))


@pytest.fixture
def classify_test_notice():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 첨부분류 대상 임시 공고",
                url="https://example.grib-test.kr/notice/classify-attachments-test",
            ).returning(notice.c.id)
        ).scalar_one()
    yield notice_id
    with engine.begin() as conn:
        conn.execute(delete(notice_score).where(notice_score.c.notice_id == notice_id))
        conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_classify_from_attachments_adds_new_topic_when_threshold_met(attachment_classify_topic, classify_test_notice):
    docs = [{"extract_ok": True, "text": "이 사업은 스마트팩토리 구축을 목표로 한다."}]
    with engine.begin() as conn:
        _classify_from_attachments(conn, classify_test_notice, docs)
        rows = conn.execute(
            select(notice_score.c.interest_topic_id, notice_score.c.reason)
            .where(notice_score.c.notice_id == classify_test_notice)
        ).all()
    assert any(r.interest_topic_id == attachment_classify_topic for r in rows)
    assert any("첨부문서" in r.reason for r in rows)


def test_classify_from_attachments_skips_below_threshold(attachment_classify_topic, classify_test_notice):
    # "약한신호"는 weight=1 — L2_ATTACHMENT_PROMOTE_THRESHOLD(4)에 못 미쳐 통과 못 해야 한다.
    assert L2_ATTACHMENT_PROMOTE_THRESHOLD == 4
    docs = [{"extract_ok": True, "text": "이 문서엔 약한신호만 있다."}]
    with engine.begin() as conn:
        _classify_from_attachments(conn, classify_test_notice, docs)
        rows = conn.execute(
            select(notice_score.c.id).where(
                notice_score.c.notice_id == classify_test_notice, notice_score.c.interest_topic_id == attachment_classify_topic
            )
        ).all()
    assert rows == []


def test_classify_from_attachments_ignores_failed_extraction_docs(attachment_classify_topic, classify_test_notice):
    docs = [{"extract_ok": False, "text": None, "error": "추출 실패"}]
    with engine.begin() as conn:
        _classify_from_attachments(conn, classify_test_notice, docs)
        rows = conn.execute(select(notice_score.c.id).where(notice_score.c.notice_id == classify_test_notice)).all()
    assert rows == []


def test_classify_from_attachments_does_not_duplicate_existing_topic(attachment_classify_topic, classify_test_notice):
    # rescan_notice_scores()와 같은 원칙 — 이미 사람이 검토·확정한 분류(또는 제목 매칭으로
    # 먼저 붙은 분류)를 자동 재계산이 덮어쓰거나 중복 추가하면 안 됨.
    with engine.begin() as conn:
        conn.execute(
            insert(notice_score).values(
                notice_id=classify_test_notice, interest_topic_id=attachment_classify_topic, l2_score=4,
                reason="제목 매칭(사전)", rule_ver=1,
            )
        )
    docs = [{"extract_ok": True, "text": "스마트팩토리 스마트팩토리 스마트팩토리"}]
    with engine.begin() as conn:
        _classify_from_attachments(conn, classify_test_notice, docs)
        rows = conn.execute(
            select(notice_score.c.id).where(
                notice_score.c.notice_id == classify_test_notice, notice_score.c.interest_topic_id == attachment_classify_topic
            )
        ).all()
    assert len(rows) == 1
