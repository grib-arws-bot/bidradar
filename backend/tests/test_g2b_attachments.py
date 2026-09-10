"""app/services/g2b_attachments.py 검증 — 나라장터 g2b 계열(입찰공고·사전규격·발주계획)
첨부(또는 인라인 텍스트) 발견 로직. analysis_pilot.py의 500줄 상한으로 분리된 모듈이라
테스트도 함께 분리했다(2026-09-08).
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import raw_payload, source
from app.services.g2b_attachments import (
    _discover_g2b_attachments,
    _g2b_bid_attachments,
    _g2b_orderplan_docs,
    _g2b_prestandard_attachments,
    _should_skip_by_name,
)


def test_should_skip_by_name_matches_routine_document_keywords():
    assert _should_skip_by_name("신청서 양식.hwp") is True
    assert _should_skip_by_name("연구시설장비비 통합관리제 매뉴얼.pdf") is True
    assert _should_skip_by_name("2026년도 로봇산업기술개발사업 공고문.hwpx") is False


def test_should_skip_by_name_ignores_whitespace_inside_keyword():
    # 실측(2026-09-05, 로봇산업기술개발사업 공고): "붙임 03. 관련 법령 및 규정.zip"처럼 키워드
    # 중간에 띄어쓰기가 들어간 실제 파일명이 있다 — 그대로 부분일치하면 놓친다.
    assert _should_skip_by_name("붙임 03. 관련 법령 및 규정.zip") is True


def test_should_skip_by_name_excludes_common_project_documents():
    # 2026-09-08 사용자 지시 — 제출서류·규정·법령·사용법은 대부분 과제에서 공통되는 문서라
    # 분석 대상에서 제외해야 한다(매뉴얼·양식은 이미 커버).
    assert _should_skip_by_name("[붙임3] 제출서류 서식.zip") is True
    assert _should_skip_by_name("4. 국가연구개발혁신법 시행규정.hwp") is True
    assert _should_skip_by_name("연구윤리 관련 법령집.pdf") is True
    assert _should_skip_by_name("시스템 사용법 안내.pdf") is True


def test_should_skip_by_name_keeps_core_project_documents():
    # 같은 지시 — 공고·기획서·개요서·과업지시서·RFP·지표는 꼭 분석해야 하는 자료라 절대
    # 제외되면 안 된다.
    for name in (
        "2026년도 로봇산업기술개발사업 공고문.hwpx",
        "사업 기획서.hwp",
        "연구개발과제 개요서.hwp",
        "과업지시서.pdf",
        "제안요청서(RFP).pdf",
        "성과지표 정의서.xlsx",
    ):
        assert _should_skip_by_name(name) is False, name


# ---- 나라장터 입찰공고정보서비스(2026-09-04, 09-06 재조회 방식으로 변경, 09-08 명세서
# 심층분석으로 sptDscrptDocUrl·stdNtceDocUrl 추가) ------------------------------------------

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


def test_discover_g2b_attachments_filters_by_name_keyword_and_finds_by_bidntceno():
    with engine.connect() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")).scalar_one()
        with mock.patch("app.services.g2b_attachments.fetch_openapi_items", return_value=[_G2B_SAMPLE_ITEM]):
            found = _discover_g2b_attachments(conn, source_id, "R26TEST9001", None, None)
    assert found == [{"name": "(붙임1) 공고문.hwp", "download_url": "https://www.g2b.go.kr/download1", "inline_text": None}]


def test_discover_g2b_attachments_no_match_returns_empty():
    with engine.connect() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")).scalar_one()
        with mock.patch("app.services.g2b_attachments.fetch_openapi_items", return_value=[_G2B_SAMPLE_ITEM]):
            assert _discover_g2b_attachments(conn, source_id, "존재하지않는공고번호", None, None) == []


def test_discover_g2b_attachments_no_notice_no_returns_empty():
    # 발주계획현황서비스는 notice_no 자체를 안 매핑한다 — None이면 API를 재조회할 필요도 없음.
    with engine.connect() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")).scalar_one()
        with mock.patch("app.services.g2b_attachments.fetch_openapi_items") as mock_fetch_items:
            assert _discover_g2b_attachments(conn, source_id, None, None, None) == []
        mock_fetch_items.assert_not_called()


def _make_temp_bid_source(conn) -> int:
    """실제 소스(raw_payload에 진짜 수집 데이터가 있음)를 건드리지 않는 격리된 임시 소스 —
    2026-09-08 실제 소스를 테스트에 재사용하다 캐시를 삭제해버린 사고 재발 방지."""
    return conn.execute(
        insert(source)
        .values(
            name="테스트 소스(g2b 캐시)", org_name="테스트기관", channel_name="테스트기관",
            base_url="https://apis.data.go.kr/test/BidPublicInfoService/testOp", stage="입찰공고",
            adapter_type="openapi", frequency_minutes=1440, is_system=False, skip_l1=True, active=True,
            legal_tier="A", auto_extract=True, auto_analyze=False,
        )
        .returning(source.c.id)
    ).scalar_one()


def test_discover_g2b_attachments_uses_raw_payload_cache_without_live_refetch():
    from app.models import source_config

    # 2026-09-09 사용자 지적 — "재분석"·오래된 백로그 재처리(prefetched_item 없음)도 이
    # 공고 하나 때문에 목록 API를 통째로 재호출할 필요 없다. raw_payload에 원본이 남아있으면
    # 거기서 찾고 apis.data.go.kr을 아예 안 불러야 한다.
    with engine.begin() as conn:
        source_id = _make_temp_bid_source(conn)
        conn.execute(insert(source_config).values(
            source_id=source_id, ver=1, config={"endpoint": "https://apis.data.go.kr/test/BidPublicInfoService/testOp"},
        ))
        conn.execute(insert(raw_payload).values(source_id=source_id, endpoint="test", body={"items": [_G2B_SAMPLE_ITEM]}))
    try:
        with engine.connect() as conn:
            with mock.patch("app.services.g2b_attachments.fetch_openapi_items") as mock_fetch_items:
                found = _discover_g2b_attachments(conn, source_id, "R26TEST9001", None, None)
            mock_fetch_items.assert_not_called()  # 캐시에서 찾았으니 라이브 재조회가 아예 없어야 함
        assert found == [{"name": "(붙임1) 공고문.hwp", "download_url": "https://www.g2b.go.kr/download1", "inline_text": None}]
    finally:
        with engine.begin() as conn:
            conn.execute(delete(raw_payload).where(raw_payload.c.source_id == source_id))
            conn.execute(delete(source_config).where(source_config.c.source_id == source_id))
            conn.execute(delete(source).where(source.c.id == source_id))


def test_discover_g2b_attachments_falls_back_to_live_when_not_in_cache():
    from app.models import source_config

    # raw_payload에 이 소스 캐시가 아예 없으면(한 번도 다시 수집 안 한 아주 오래된 경우)
    # 기존처럼 실시간 재조회로 안전하게 폴백해야 한다.
    with engine.begin() as conn:
        source_id = _make_temp_bid_source(conn)
        conn.execute(insert(source_config).values(
            source_id=source_id, ver=1, config={"endpoint": "https://apis.data.go.kr/test/BidPublicInfoService/testOp"},
        ))
    try:
        with engine.connect() as conn:
            with mock.patch("app.services.g2b_attachments.fetch_openapi_items", return_value=[_G2B_SAMPLE_ITEM]) as mock_fetch_items:
                found = _discover_g2b_attachments(conn, source_id, "R26TEST9001", None, None)
            mock_fetch_items.assert_called_once()
        assert found == [{"name": "(붙임1) 공고문.hwp", "download_url": "https://www.g2b.go.kr/download1", "inline_text": None}]
    finally:
        with engine.begin() as conn:
            conn.execute(delete(source_config).where(source_config.c.source_id == source_id))
            conn.execute(delete(source).where(source.c.id == source_id))


def test_g2b_bid_attachments_includes_site_description_and_standard_notice_docs():
    # 2026-09-08 공식 명세서(v1.2) 심층분석으로 확인 — sptDscrptDocUrl1~5(현장설명서, 파일명
    # 필드 없음)·stdNtceDocUrl(표준공고서 1건)을 그동안 놓치고 있었다.
    item = {
        **_G2B_SAMPLE_ITEM,
        "sptDscrptDocUrl1": "https://www.g2b.go.kr/site-desc-1?fileNm=현장설명서.hwp",
        "sptDscrptDocUrl2": "",
        "stdNtceDocUrl": "https://www.g2b.go.kr/std-notice",
    }
    found = _g2b_bid_attachments(item)
    names = [f["name"] for f in found]
    assert "현장설명서.hwp" in names
    assert "표준공고서" in names  # 파일명 쿼리파라미터 없으면 순번 없는 고정 이름으로 대체


def test_g2b_bid_attachments_site_description_respects_name_skip_filter():
    item = {**_G2B_SAMPLE_ITEM, "sptDscrptDocUrl1": "https://www.g2b.go.kr/x?fileNm=관련법령.hwp"}
    found = _g2b_bid_attachments(item)
    assert "관련법령.hwp" not in [f["name"] for f in found]


# ---- 사전규격정보서비스(2026-09-06) — specDocFileUrl1~5뿐이고 파일명 필드가 없다. 기존
# 코드는 ntceSpecDocUrl을 찾고 있어서 이 계열은 100% 못 찾고 있었던 별개 버그였다. ----------

_G2B_PRESTANDARD_SAMPLE_ITEM = {
    "bfSpecRgstNo": "R26TEST8001",
    "specDocFileUrl1": "https://www.g2b.go.kr/pn/pnz/pnza/UntyAtchFile/downloadFile.do?bfSpecRegNo=R26TEST8001&fileType=BFDTL&fileSeq=1&fileNm=%EA%B7%9C%EA%B2%A9%EC%84%9C.hwp",
    "specDocFileUrl2": "https://www.g2b.go.kr/pn/pnz/pnza/UntyAtchFile/downloadFile.do?bfSpecRegNo=R26TEST8001&fileType=BFDTL&fileSeq=2",
}


def test_g2b_prestandard_attachments_uses_filename_query_param_when_present():
    found = _g2b_prestandard_attachments(_G2B_PRESTANDARD_SAMPLE_ITEM)
    assert found[0]["name"] == "규격서.hwp"
    assert found[0]["download_url"] == _G2B_PRESTANDARD_SAMPLE_ITEM["specDocFileUrl1"]


def test_g2b_prestandard_attachments_falls_back_to_sequence_number_without_filename():
    found = _g2b_prestandard_attachments(_G2B_PRESTANDARD_SAMPLE_ITEM)
    assert found[1]["name"] == "규격서2"


def test_discover_g2b_attachments_dispatches_to_prestandard_family_by_endpoint():
    with engine.connect() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "나라장터 사전규격정보서비스(용역)")).scalar_one()
        with mock.patch("app.services.g2b_attachments.fetch_openapi_items", return_value=[_G2B_PRESTANDARD_SAMPLE_ITEM]):
            found = _discover_g2b_attachments(conn, source_id, "R26TEST8001", None, None)
    assert [f["name"] for f in found] == ["규격서.hwp", "규격서2"]


# ---- 발주계획현황서비스(2026-09-06) — 목록조회 응답엔 다운로드 URL이 없고 규격 내용을
# API 응답 텍스트로 직접 준다(실측상 거의 항상 공백, 2026-09-08). 다운로드·문서추출 없이
# 텍스트 그대로 문서로 남긴다. 진짜 첨부파일 전용 오퍼레이션(getOrderPlanSttusAtchFileList)은
# 명세서로 확인했으나 활용신청 확인 전이라 아직 연동 안 함(구현스펙.md 향후 과제). --------------

_G2B_ORDERPLAN_SAMPLE_ITEM = {
    "orderPlanUntyNo": "R26TEST7001",
    "specCntnts": "스마트제조 장비 IoT 연계 모니터링 운영 용역 — 규격 개요",
    "specItemNm1": "모니터링 대상",
    "specItemCntnts1": "소상공인 스마트공장 설비 500개소",
    "specItemNm2": "",
    "specItemCntnts2": "",
}


def test_g2b_orderplan_docs_builds_inline_text_tasks_and_skips_empty_items():
    docs = _g2b_orderplan_docs(_G2B_ORDERPLAN_SAMPLE_ITEM)
    names = [d["name"] for d in docs]
    assert names == ["규격내용", "모니터링 대상"]  # 2번 항목은 이름·내용 다 비어 있어 제외
    assert all(d["download_url"] is None for d in docs)
    assert docs[0]["inline_text"] == _G2B_ORDERPLAN_SAMPLE_ITEM["specCntnts"]


def test_discover_g2b_attachments_dispatches_to_orderplan_family_by_extra_field():
    # 발주계획은 notice.notice_no가 아니라 extra.orderPlanUntyNo로 매칭한다.
    with engine.connect() as conn:
        source_id = conn.execute(select(source.c.id).where(source.c.name == "나라장터 발주계획현황서비스(용역)")).scalar_one()
        with mock.patch("app.services.g2b_attachments.fetch_openapi_items", return_value=[_G2B_ORDERPLAN_SAMPLE_ITEM]):
            found = _discover_g2b_attachments(
                conn, source_id, None, {"orderPlanUntyNo": "R26TEST7001"}, None
            )
    assert [f["name"] for f in found] == ["규격내용", "모니터링 대상"]
    assert found[0]["inline_text"] is not None
