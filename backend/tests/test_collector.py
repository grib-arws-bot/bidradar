"""U11 완료조건 검증: 어댑터·매퍼·스코어러(L1/L2) 단위 테스트. run_source() 통합 테스트는
test_runner.py에 있음(500줄 상한 초과로 분리, 2026-09-02)."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from sqlalchemy import delete, func, insert, select

from app.collector.adapters.openapi import fetch_openapi_items
from app.collector.mapper import map_item
from app.collector.runner import _collection_window, _get_or_create_org
from app.collector.scorer import L2_PROMOTE_THRESHOLD, score_l2
from app.collector.work_type import guess_work_type
from app.db import engine
from app.models import interest_topic, keyword_rule, org, source, source_run

SAMPLE_ITEMS = [
    {
        "bidNtceNo": "R26TEST0001",
        "bidNtceNm": "지능형 CCTV 통합관제시스템 구축",
        "ntceInsttNm": "테스트발주기관",
        "bidNtceDt": "202609010900",
        "bidClseDt": "202609201800",
        "presmptPrce": "512,000,000",
        "bidNtceDtlUrl": "https://www.g2b.go.kr/bid/R26TEST0001",
    },
    {
        "bidNtceNo": "R26TEST0002",
        "bidNtceNm": "청사 화장실 리모델링",
        "ntceInsttNm": "테스트발주기관",
        "bidNtceDt": "202609020900",
        "bidClseDt": "202609211800",
        "presmptPrce": "80,000,000",
        "bidNtceDtlUrl": "https://www.g2b.go.kr/bid/R26TEST0002",
    },
]

FIELD_MAPS = [
    {"target_field": "notice_no", "source_path": "$.bidNtceNo", "format_hint": None},
    {"target_field": "title", "source_path": "$.bidNtceNm", "format_hint": None},
    {"target_field": "org_name", "source_path": "$.ntceInsttNm", "format_hint": None},
    {"target_field": "open_dt", "source_path": "$.bidNtceDt", "format_hint": "%Y%m%d%H%M"},
    {"target_field": "close_dt", "source_path": "$.bidClseDt", "format_hint": "%Y%m%d%H%M"},
    {"target_field": "est_price", "source_path": "$.presmptPrce", "format_hint": None},
    {"target_field": "url", "source_path": "$.bidNtceDtlUrl", "format_hint": None},
]


def _bid_service_source_id() -> int:
    with engine.connect() as conn:
        row = conn.execute(select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")).first()
    assert row, "U2 시드가 먼저 실행돼 있어야 함"
    return row[0]


# ---- 어댑터 ----------------------------------------------------------------


def test_fetch_openapi_items_parses_response_and_builds_params(monkeypatch):
    mock_response = mock.Mock()
    mock_response.json.return_value = {"response": {"body": {"items": SAMPLE_ITEMS}}}
    mock_fetch = mock.Mock(return_value=mock_response)
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock_fetch)

    config = {
        "endpoint": "https://apis.data.go.kr/1230000/BidPublicInfoService/getBidPblancListInfoServc",
        "params": {"type": "json"},
        "date_range_params": {"begin": "inqryBgnDt", "end": "inqryEndDt", "format": "%Y%m%d%H%M"},
        "items_path": "$.response.body.items[*]",
    }

    now = datetime.now(timezone.utc)
    items = fetch_openapi_items(config, "test-service-key", begin=now - timedelta(days=3), end=now)

    assert items == SAMPLE_ITEMS
    call_args = mock_fetch.call_args
    assert call_args.args[0] == config["endpoint"]
    sent_params = call_args.kwargs["params"]
    assert sent_params["ServiceKey"] == "test-service-key"
    assert "inqryBgnDt" in sent_params and "inqryEndDt" in sent_params


def test_fetch_openapi_items_raises_on_quota_exceeded_error_envelope(monkeypatch):
    # 2026-09-08 실측 — 일일 요청한도 초과 시 data.go.kr이 200 OK로 이 에러 봉투를 돌려주는데,
    # items_path와 안 겹쳐 예전엔 조용히 빈 리스트로 처리됐다(할당량 초과가 "신규 공고 없음"과
    # 구분 안 됨, CLAUDE.md S8 "조용한 빈 결과 금지"). 이제는 예외로 명확히 알려야 한다.
    mock_response = mock.Mock()
    mock_response.json.return_value = {
        "OpenAPI_ServiceResponse": {
            "cmmMsgHeader": {
                "errMsg": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR",
                "returnAuthMsg": "일일 서비스 요청제한 횟수 초과 에러",
                "returnReasonCode": "22",
            }
        }
    }
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock.Mock(return_value=mock_response))

    config = {
        "endpoint": "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc",
        "params": {"type": "json"},
        "items_path": "$.response.body.items[*]",
    }
    now = datetime.now(timezone.utc)
    with pytest.raises(RuntimeError, match="LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"):
        fetch_openapi_items(config, "test-service-key", begin=now - timedelta(days=3), end=now)


def test_fetch_openapi_items_raises_on_service_level_result_code_error(monkeypatch):
    # 2026-09-08 명세서 심층분석으로 확인 — 포털 게이트(cmmMsgHeader)를 통과한 뒤에도 서비스
    # 자체가 response.header.resultCode로 에러를 알린다("00"=정상, "03"=데이터없음(정상),
    # 그 외는 에러). 이것도 items_path와 안 겹쳐 예전엔 조용히 빈 리스트가 됐다.
    mock_response = mock.Mock()
    mock_response.json.return_value = {
        "response": {
            "header": {"resultCode": "08", "resultMsg": "필수값 입력 에러"},
            "body": {"items": []},
        }
    }
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock.Mock(return_value=mock_response))

    config = {
        "endpoint": "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService/getOrderPlanSttusListServc",
        "params": {"type": "json"},
        "items_path": "$.response.body.items[*]",
    }
    now = datetime.now(timezone.utc)
    with pytest.raises(RuntimeError, match="resultCode=08"):
        fetch_openapi_items(config, "test-service-key", begin=now - timedelta(days=3), end=now)


def test_fetch_openapi_items_result_code_03_no_data_is_not_an_error(monkeypatch):
    # resultCode "03"(데이터 없음)은 명세서상 정상 응답이다 — 예외를 던지면 안 된다.
    mock_response = mock.Mock()
    mock_response.json.return_value = {
        "response": {"header": {"resultCode": "03", "resultMsg": "NO_DATA"}, "body": {"items": []}}
    }
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock.Mock(return_value=mock_response))

    config = {
        "endpoint": "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService/getOrderPlanSttusListServc",
        "params": {"type": "json"},
        "items_path": "$.response.body.items[*]",
    }
    now = datetime.now(timezone.utc)
    items = fetch_openapi_items(config, "test-service-key", begin=now - timedelta(days=3), end=now)
    assert items == []


def test_fetch_openapi_items_month_param_uses_end_yyyymm(monkeypatch):
    # K-water 3종(2026-09-03 실측) — begin/end 쌍이 아니라 "검색년월(YYYYMM)" 파라미터
    # 하나만 받는다. end 기준 월로 채워야 한다.
    mock_response = mock.Mock()
    mock_response.json.return_value = {"response": {"body": {"items": SAMPLE_ITEMS}}}
    mock_fetch = mock.Mock(return_value=mock_response)
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock_fetch)

    config = {
        "endpoint": "http://opendata.kwater.or.kr/openapi-data/service/pubd/ebid/tndr/dmscpt/list",
        "params": {"_type": "json"},
        "month_param": "searchDt",
        "items_path": "$.response.body.items[*]",
    }

    end = datetime(2026, 9, 3, tzinfo=timezone.utc)
    begin = end - timedelta(days=20)
    items = fetch_openapi_items(config, "test-service-key", begin=begin, end=end)

    assert items == SAMPLE_ITEMS
    sent_params = mock_fetch.call_args.kwargs["params"]
    assert sent_params["searchDt"] == "202609"
    assert "inqryBgnDt" not in sent_params


def test_fetch_openapi_items_post_method_sends_form_body(monkeypatch):
    # advisory INBOX #3(2026-09-01) — IRIS 접수예정은 서비스키 없는 내부 JSON 엔드포인트를
    # POST 폼바디로 호출해야 실제 데이터가 나온다(GET으로 페이지 자체를 열면 빈 템플릿만 옴).
    mock_response = mock.Mock()
    mock_response.json.return_value = {"listBsnsAncmBtinSitu": SAMPLE_ITEMS}
    mock_fetch = mock.Mock(return_value=mock_response)
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock_fetch)

    config = {
        "endpoint": "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do",
        "method": "POST",
        "params": {"pageIndex": "1"},
        "items_path": "$.listBsnsAncmBtinSitu[*]",
    }
    now = datetime.now(timezone.utc)
    items = fetch_openapi_items(config, None, begin=now, end=now)

    assert items == SAMPLE_ITEMS
    call_args = mock_fetch.call_args
    assert call_args.args[0] == config["endpoint"]
    assert call_args.kwargs["method"] == "POST"
    assert call_args.kwargs["data"]["pageIndex"] == "1"
    assert "params" not in call_args.kwargs


def test_fetch_openapi_items_paginates_until_total_pages_reached(monkeypatch):
    # 2026-09-02 — IRIS처럼 date_range_params 없이 페이지만 넘기는 API용. 첫 응답의
    # paginationInfo.totalPageCount를 읽어 그 페이지까지만 돈다(무한루프 방지).
    page1 = mock.Mock()
    page1.json.return_value = {
        "listBsnsAncmBtinSitu": [{"ancmId": "1"}, {"ancmId": "2"}],
        "paginationInfo": {"totalPageCount": 2},
    }
    page2 = mock.Mock()
    page2.json.return_value = {"listBsnsAncmBtinSitu": [{"ancmId": "3"}], "paginationInfo": {"totalPageCount": 2}}
    mock_fetch = mock.Mock(side_effect=[page1, page2])
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock_fetch)

    config = {
        "endpoint": "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do",
        "method": "POST",
        "params": {"pageIndex": "1"},
        "items_path": "$.listBsnsAncmBtinSitu[*]",
        "pagination": {"page_param": "pageIndex", "total_path": "$.paginationInfo.totalPageCount", "max_pages": 20},
    }
    now = datetime.now(timezone.utc)
    items = fetch_openapi_items(config, None, begin=now, end=now)

    assert [i["ancmId"] for i in items] == ["1", "2", "3"]
    assert mock_fetch.call_count == 2
    assert mock_fetch.call_args_list[0].kwargs["data"]["pageIndex"] == "1"
    assert mock_fetch.call_args_list[1].kwargs["data"]["pageIndex"] == "2"


def test_fetch_openapi_items_pagination_stops_on_empty_page(monkeypatch):
    # total_path가 없거나 응답이 이상해도 빈 페이지가 나오면 멈춘다(안전장치).
    page1 = mock.Mock()
    page1.json.return_value = {"listBsnsAncmBtinSitu": [{"ancmId": "1"}]}
    page2 = mock.Mock()
    page2.json.return_value = {"listBsnsAncmBtinSitu": []}
    mock_fetch = mock.Mock(side_effect=[page1, page2])
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock_fetch)

    config = {
        "endpoint": "https://example.grib-test.kr",
        "items_path": "$.listBsnsAncmBtinSitu[*]",
        "pagination": {"page_param": "pageIndex", "max_pages": 20},
    }
    now = datetime.now(timezone.utc)
    items = fetch_openapi_items(config, None, begin=now, end=now)
    assert [i["ancmId"] for i in items] == ["1"]
    assert mock_fetch.call_count == 2


def test_fetch_openapi_items_parses_xml_response(monkeypatch):
    # 2026-09-02 — 과기정통부 사업공고 API가 type=json을 보내도 실제로는 XML만 돌려줌을
    # 실측으로 확인(라이브 서비스키로 직접 호출). item이 1건이어도 리스트로 나와야 한다.
    xml_body = """<?xml version="1.0" encoding="UTF-8"?>
    <response>
        <header><resultCode>00</resultCode><resultMsg>NORMAL_CODE</resultMsg></header>
        <body>
            <items>
                <item>
                    <subject>2026년 사업 공고</subject>
                    <viewUrl>https://msit.example/1</viewUrl>
                    <managerName>홍길동</managerName>
                </item>
                <numOfRows>10</numOfRows>
                <pageNo>1</pageNo>
                <totalCount>1</totalCount>
            </items>
        </body>
    </response>"""
    mock_response = mock.Mock()
    mock_response.content = xml_body.encode("utf-8")
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock.Mock(return_value=mock_response))

    config = {
        "endpoint": "https://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList",
        "format": "xml",
        "params": {"type": "json"},
        "items_path": "$.response.body.items.item[*]",
    }
    now = datetime.now(timezone.utc)
    items = fetch_openapi_items(config, None, begin=now, end=now)

    assert len(items) == 1
    assert items[0]["subject"] == "2026년 사업 공고"
    assert items[0]["managerName"] == "홍길동"  # 어댑터는 원문 그대로 반환 — 마스킹은 runner의 몫


# ---- 수집 기간(직전 성공 이후~지금, 없으면 2개월 캡, 2026-09-01 결정) ------------------


def test_collection_window_uses_last_ok_run_with_one_hour_overlap():
    source_id = _bid_service_source_id()
    # 시드 데이터가 이 소스에 무작위 status의 source_run 30일치를 이미 넣어뒀으므로, "지금"보다
    # 살짝 이전 시각을 넣으면 그 어떤 시드 이력보다도 최신이라 func.max()가 이걸 고르게 된다 —
    # 기존 이력을 지우지 않고도(다른 테스트·현재 켜진 데모 화면에 영향 없이) 검증 가능하다.
    last_ok = datetime.now(timezone.utc) - timedelta(seconds=1)
    with engine.begin() as conn:
        run_id = conn.execute(
            insert(source_run).values(source_id=source_id, run_at=last_ok, status="ok", items_fetched=1).returning(
                source_run.c.id
            )
        ).scalar_one()
    try:
        with engine.connect() as conn:
            begin, _end = _collection_window(conn, source_id, max_lookback_days=60)
        assert begin == last_ok - timedelta(hours=1)
    finally:
        with engine.begin() as conn:
            conn.execute(delete(source_run).where(source_run.c.id == run_id))


def test_collection_window_caps_at_max_lookback_when_no_success_history():
    # source_run이 아예 없는 소스(존재하지 않는 source_id로도 충분 — 함수가 source 테이블은 안 봄)
    with engine.connect() as conn:
        begin, end = _collection_window(conn, source_id=-1, max_lookback_days=60)
    assert end - begin == timedelta(days=60)


# ---- 발주기관 자동 등록 시 채널(source_id) 연결 — 2026-09-01 요청 ---------------------


def test_get_or_create_org_sets_source_id_for_new_org():
    source_id = _bid_service_source_id()
    unique_name = "테스트전용발주기관_agency_link"
    with engine.begin() as conn:
        conn.execute(delete(org).where(org.c.name == unique_name))  # 혹시 이전 실행 잔여물 정리
        try:
            org_id = _get_or_create_org(conn, unique_name, source_id)
            saved_source_id = conn.execute(select(org.c.source_id).where(org.c.id == org_id)).scalar_one()
            assert saved_source_id == source_id
        finally:
            conn.execute(delete(org).where(org.c.name == unique_name))


# ---- 사업유형 제목 기반 추정(근사치, 2026-09-01 요청) ----------------------------


def test_guess_work_type_matches_common_titles():
    assert guess_work_type("CCTV 임대 및 유지보수") == "유지보수"  # 겹쳐도 더 구체적인 신호 우선
    assert guess_work_type("관제실 청소용역") == "운영"
    assert guess_work_type("전자칠판 보급사업") == "구매"
    assert guess_work_type("지능형 CCTV 통합관제시스템 구축") == "구축"


def test_guess_work_type_returns_none_when_no_keyword_matches():
    assert guess_work_type("아무 키워드도 없는 제목") is None


# ---- 매퍼 --------------------------------------------------------------


def test_map_item_success():
    mapped = map_item(SAMPLE_ITEMS[0], FIELD_MAPS)
    assert mapped is not None
    assert mapped["title"] == "지능형 CCTV 통합관제시스템 구축"
    assert mapped["est_price"] == 512_000_000  # 콤마 제거+정수 변환
    assert mapped["open_dt"].year == 2026 and mapped["open_dt"].month == 9


def test_map_item_missing_required_field_returns_none():
    broken = {**SAMPLE_ITEMS[0], "bidNtceNm": ""}
    assert map_item(broken, FIELD_MAPS) is None


def test_map_item_succeeds_without_open_dt():
    # 2026-09-05 — open_dt를 필수 필드에서 뺐다(사전규격·발주계획처럼 정식 입찰 시작일 자체가
    # 없는 소스가 있어서). open_dt가 아예 안 매핑돼도(field_maps에 없어도) 나머지 3개
    # (title/org_name/url)만 있으면 정상 매핑되고, open_dt는 그냥 없는 채로 결과에 남는다.
    field_maps_without_open_dt = [fm for fm in FIELD_MAPS if fm["target_field"] != "open_dt"]
    mapped = map_item(SAMPLE_ITEMS[0], field_maps_without_open_dt)
    assert mapped is not None
    assert mapped.get("open_dt") is None


def test_map_item_const_prefix_sets_fixed_value_regardless_of_item():
    # advisory INBOX #2 — 과기정통부 사업공고처럼 발주기관이 응답 필드가 아니라 소스 전체
    # 고정값인 경우. close_dt가 아예 없는 소스도 흉내낸다(마감일 없는 공고, INBOX #1).
    field_maps = [
        {"target_field": "title", "source_path": "$.subject", "format_hint": None},
        {"target_field": "org_name", "source_path": "const:과학기술정보통신부", "format_hint": None},
        {"target_field": "open_dt", "source_path": "$.pressDt", "format_hint": "%Y%m%d"},
        {"target_field": "url", "source_path": "$.viewUrl", "format_hint": None},
    ]
    item = {"subject": "2026년도 R&D 사업 공고", "pressDt": "20260901", "viewUrl": "https://msit.example/1"}
    mapped = map_item(item, field_maps)
    assert mapped is not None
    assert mapped["org_name"] == "과학기술정보통신부"
    assert mapped.get("close_dt") is None  # 매핑 자체가 없으므로 항상 None — 필수 필드가 아니라 통과됨


def test_map_item_urlfmt_prefix_builds_url_from_item_field():
    # 2026-09-10 — 사전규격정보서비스는 응답에 상세페이지 URL이 없어 bfSpecRgstNo로 직접
    # 조립한다(사용자가 브라우저에서 실제 URL 패턴을 확인해줌, 의사결정_로그 참고). 쿼리
    # 파라미터명(bfSpecRegNo)과 응답 필드명(bfSpecRgstNo)의 철자가 다른 점에 유의.
    field_maps = [
        {"target_field": "title", "source_path": "$.prdctClsfcNoNm", "format_hint": None},
        {"target_field": "org_name", "source_path": "const:테스트기관", "format_hint": None},
        {
            "target_field": "url",
            "source_path": "urlfmt:https://www.g2b.go.kr/link/PRVA004_02/?bfSpecRegNo={bfSpecRgstNo}",
            "format_hint": None,
        },
    ]
    item = {"prdctClsfcNoNm": "테스트 사전규격", "bfSpecRgstNo": "R26BD00273379"}
    mapped = map_item(item, field_maps)
    assert mapped is not None
    assert mapped["url"] == "https://www.g2b.go.kr/link/PRVA004_02/?bfSpecRegNo=R26BD00273379"


def test_map_item_urlfmt_prefix_missing_field_returns_none_url():
    field_maps = [
        {"target_field": "title", "source_path": "$.prdctClsfcNoNm", "format_hint": None},
        {"target_field": "org_name", "source_path": "const:테스트기관", "format_hint": None},
        {"target_field": "url", "source_path": "urlfmt:https://x/{bfSpecRgstNo}", "format_hint": None},
    ]
    item = {"prdctClsfcNoNm": "테스트 사전규격"}  # bfSpecRgstNo 없음
    assert map_item(item, field_maps) is None  # url이 REQUIRED_FIELDS라 통째로 skip


def test_map_item_handles_unquoted_json_integer_date():
    # K-water 3종(2026-09-03 실측) — 날짜가 따옴표 없는 JSON 숫자로 온다(예: 20260903).
    # strptime은 str만 받으므로 이전엔 TypeError로 죽었다.
    field_maps = [
        {"target_field": "title", "source_path": "$.tndrPblancNm", "format_hint": None},
        {"target_field": "org_name", "source_path": "const:한국수자원공사", "format_hint": None},
        {"target_field": "open_dt", "source_path": "$.tndrPblancDe", "format_hint": "%Y%m%d"},
        {"target_field": "url", "source_path": "$.url", "format_hint": None},
    ]
    item = {"tndrPblancNm": "대청댐 노후관 개량사업", "tndrPblancDe": 20260903, "url": "https://ebid.kwater.or.kr/fz?bidno=B1"}
    mapped = map_item(item, field_maps)
    assert mapped is not None
    assert mapped["open_dt"].year == 2026 and mapped["open_dt"].month == 9 and mapped["open_dt"].day == 3


def test_map_item_treats_year_9999_sentinel_date_as_missing():
    # 2026-09-08 실측 — IRIS는 접수기간이 "미정"인 공고에 빈 문자열 대신 "9999.12.31" 같은
    # sentinel을 준다(실제 사례: "장애인·노인 자립생활 보조기기" 공고, rcveStrDe=rcveEndDe=
    # "9999.12.31"). 그대로 파싱하면 화면에 연도 9999 날짜가 뜬다 — None으로 취급해야 한다.
    field_maps = [
        {"target_field": "title", "source_path": "$.ancmTl", "format_hint": None},
        {"target_field": "org_name", "source_path": "$.sorgnNm", "format_hint": None},
        {"target_field": "open_dt", "source_path": "$.rcveStrDe", "format_hint": "%Y.%m.%d"},
        {"target_field": "close_dt", "source_path": "$.rcveEndDe", "format_hint": "%Y.%m.%d"},
        {"target_field": "url", "source_path": "$.url", "format_hint": None},
    ]
    item = {
        "ancmTl": "테스트 공고", "sorgnNm": "테스트기관",
        "rcveStrDe": "9999.12.31", "rcveEndDe": "9999.12.31",
        "url": "https://www.iris.go.kr/test",
    }
    mapped = map_item(item, field_maps)
    assert mapped is not None
    assert mapped["open_dt"] is None
    assert mapped["close_dt"] is None


def test_map_item_extra_prefix_collects_into_nested_dict():
    # 2026-09-02 — IRIS 목록 응답 중 명명 컬럼에 안 들어가는 나머지를 notice.extra로 보여주는
    # 기능. "extra:원본키" 여러 개가 하나의 extra 딕셔너리로 모여야 한다.
    field_maps = FIELD_MAPS + [
        {"target_field": "extra:dDay", "source_path": "$.dDay", "format_hint": None},
        {"target_field": "extra:sorgnNm", "source_path": "$.ntceInsttNm", "format_hint": None},
    ]
    item = {**SAMPLE_ITEMS[0], "dDay": 35}
    mapped = map_item(item, field_maps)
    assert mapped is not None
    assert mapped["extra"] == {"dDay": 35, "sorgnNm": "테스트발주기관"}
    assert "extra:dDay" not in mapped  # 원본 target_field 그대로는 안 남아야 함


# ---- 스코어러(L2) --------------------------------------------------------


def test_score_l2_matches_seeded_keyword():
    with engine.connect() as conn:
        scores = score_l2(conn, "지능형 CCTV 통합관제시스템 구축")
    assert scores, "시드된 keyword_rule(지능형 CCTV 등)과 매칭돼야 함"
    best_topic_id, info = max(scores.items(), key=lambda kv: kv[1]["score"])
    # 정확한 점수는 관리자가 화면에서 키워드를 추가/삭제하면 달라질 수 있다(2026-09-05,
    # 키워드 관리 CRUD 신설) — 승급 문턱을 넘는지만 검증한다.
    assert info["score"] >= L2_PROMOTE_THRESHOLD
    assert "지능형 CCTV" in info["matched_terms"]


def test_score_l2_no_match_for_unrelated_title():
    with engine.connect() as conn:
        scores = score_l2(conn, "청사 화장실 리모델링")
    assert scores == {}


def test_every_interest_topic_has_at_least_one_keyword_rule():
    # 2026-09-02 — IRIS 실데이터 14건 전부 매칭없음으로 나온 원인이 "20개 주제 중 18개에
    # keyword_rule이 하나도 없었다"였음(관심주제 분류 대조표 참고). 이 공백이 다시 생기면
    # 조용히 재발하므로 구조적으로 막는다.
    with engine.connect() as conn:
        rows = conn.execute(
            select(interest_topic.c.name, func.count(keyword_rule.c.id))
            .select_from(interest_topic)
            .join(keyword_rule, keyword_rule.c.interest_topic_id == interest_topic.c.id, isouter=True)
            .group_by(interest_topic.c.name)
        ).all()
    empty = [name for name, count in rows if count == 0]
    assert not empty, f"keyword_rule이 없는 관심주제: {empty}"


@pytest.mark.parametrize(
    "title,expected_topic",
    [
        ("2026년도 제2차 로봇산업기술개발사업 신규지원 대상과제 공고", "로봇/자동화"),
        ("2026년도 AI 기반 주파수 간섭분석 및 전파예측기술 개발사업", "AI/데이터"),
        ("2026년도 2차 신재생에너지R&D(수소) 신규지원대상 연구개발과제 재공고", "에너지/신재생·ESS"),
        ("2026년도 NRF 인터내셔널 모빌리티 신규과제 공모", "모빌리티/자율주행"),
    ],
)
def test_score_l2_promotes_real_iris_titles_after_rule_gap_fix(title, expected_topic):
    # 2026-09-02 라이브 재수집에서 실제로 나온 IRIS 공고 제목 그대로 — 규칙 공백을 메우기 전엔
    # 전부 매칭없음이었다.
    with engine.connect() as conn:
        topic_id = conn.execute(select(interest_topic.c.id).where(interest_topic.c.name == expected_topic)).scalar_one()
        scores = score_l2(conn, title)
    assert topic_id in scores, f"'{title}'이 '{expected_topic}'에 매칭돼야 함"
    assert scores[topic_id]["score"] >= L2_PROMOTE_THRESHOLD

# 러너(run_source) 통합 테스트는 test_runner.py로 분리했다(500줄 상한, 2026-09-02).
