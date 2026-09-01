"""U11 완료조건 검증: 어댑터·매퍼·스코어러(L1/L2) + 나라장터 소스 1회 수집(목 응답).
실제 라이브 호출은 공공데이터포털 인증키가 있어야 하므로, 여기서는 url_guard.fetch를 목으로
대체해 어댑터~러너 전 구간이 올바르게 동작하는지 검증한다. 실 키가 오면
`python -m app.cli collect --source-id <id> --service-key <키>`로 마지막 확인만 하면 된다.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from sqlalchemy import delete, insert, select

from app.collector.adapters.openapi import fetch_openapi_items
from app.collector.mapper import map_item
from app.collector.runner import _collection_window, run_source
from app.collector.scorer import score_l2
from app.db import engine
from app.models import notice, notice_score, raw_payload, source, source_run

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
        row = conn.execute(select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스")).first()
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


# ---- 스코어러(L2) --------------------------------------------------------


def test_score_l2_matches_seeded_keyword():
    with engine.connect() as conn:
        scores = score_l2(conn, "지능형 CCTV 통합관제시스템 구축")
    assert scores, "시드된 keyword_rule(지능형 CCTV 등)과 매칭돼야 함"
    best_topic_id, info = max(scores.items(), key=lambda kv: kv[1]["score"])
    assert info["score"] >= 4
    assert "지능형 CCTV" in info["matched_terms"]


def test_score_l2_no_match_for_unrelated_title():
    with engine.connect() as conn:
        scores = score_l2(conn, "청사 화장실 리모델링")
    assert scores == {}


# ---- 러너(통합) -----------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_collector_side_effects():
    source_id = _bid_service_source_id()
    yield
    with engine.begin() as conn:
        test_notice_ids = [
            row[0]
            for row in conn.execute(select(notice.c.id).where(notice.c.notice_no.in_(["R26TEST0001", "R26TEST0002"])))
        ]
        if test_notice_ids:
            conn.execute(delete(notice_score).where(notice_score.c.notice_id.in_(test_notice_ids)))
            conn.execute(delete(notice).where(notice.c.id.in_(test_notice_ids)))
        conn.execute(
            delete(source_run).where(
                source_run.c.source_id == source_id,
                (source_run.c.items_fetched == 2) | (source_run.c.error_message == "네트워크 실패"),
            )
        )
        conn.execute(delete(raw_payload).where(raw_payload.c.source_id == source_id, raw_payload.c.endpoint.like("%getBidPblancListInfoServc%")))


def test_run_source_end_to_end(monkeypatch):
    mock_response = mock.Mock()
    mock_response.json.return_value = {"response": {"body": {"items": SAMPLE_ITEMS}}}
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock.Mock(return_value=mock_response))

    source_id = _bid_service_source_id()
    with engine.begin() as conn:
        result = run_source(conn, source_id)

    assert result == {"fetched": 2, "inserted": 2, "skipped": 0, "scored": 1}

    with engine.connect() as conn:
        cctv_notice = conn.execute(select(notice.c.id, notice.c.title).where(notice.c.notice_no == "R26TEST0001")).first()
        assert cctv_notice is not None
        scores = conn.execute(select(notice_score.c.l2_score).where(notice_score.c.notice_id == cctv_notice[0])).all()
        assert len(scores) == 1
        assert scores[0][0] >= 4

        run_row = conn.execute(
            select(source_run.c.status, source_run.c.items_fetched).where(source_run.c.source_id == source_id).order_by(source_run.c.id.desc())
        ).first()
        assert run_row == ("ok", 2)


def test_run_source_is_idempotent_on_rerun(monkeypatch):
    mock_response = mock.Mock()
    mock_response.json.return_value = {"response": {"body": {"items": SAMPLE_ITEMS}}}
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock.Mock(return_value=mock_response))

    source_id = _bid_service_source_id()
    with engine.begin() as conn:
        run_source(conn, source_id)
        second = run_source(conn, source_id)

    # 같은 url(공고)이 이미 있으면 새로 insert하지 않는다 — "inserted" 0.
    assert second["inserted"] == 0
    assert second["fetched"] == 2


def test_run_source_second_call_narrows_window_to_last_success(monkeypatch):
    mock_response = mock.Mock()
    mock_response.json.return_value = {"response": {"body": {"items": SAMPLE_ITEMS}}}
    mock_fetch = mock.Mock(return_value=mock_response)
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock_fetch)

    source_id = _bid_service_source_id()
    with engine.begin() as conn:
        run_source(conn, source_id)
    first_begin = mock_fetch.call_args.kwargs["params"]["inqryBgnDt"]

    with engine.begin() as conn:
        run_source(conn, source_id)
    second_begin = mock_fetch.call_args.kwargs["params"]["inqryBgnDt"]

    # 직전 성공 수집 시각을 기준으로 좁혀져야 한다 — 매번 60일 전 고정값으로 되돌아가면 안 됨
    assert second_begin > first_begin


def test_run_source_records_failure_and_reraises(monkeypatch):
    monkeypatch.setattr(
        "app.collector.adapters.openapi.fetch", mock.Mock(side_effect=RuntimeError("네트워크 실패"))
    )

    source_id = _bid_service_source_id()
    with pytest.raises(RuntimeError):
        with engine.begin() as conn:
            run_source(conn, source_id)

    with engine.connect() as conn:
        run_row = conn.execute(
            select(source_run.c.status).where(source_run.c.source_id == source_id).order_by(source_run.c.id.desc())
        ).first()
    assert run_row == ("fail",)
