"""U11 완료조건 검증: 어댑터·매퍼·스코어러(L1/L2) + 나라장터 소스 1회 수집(목 응답).
실제 라이브 호출은 공공데이터포털 인증키가 있어야 하므로, 여기서는 url_guard.fetch를 목으로
대체해 어댑터~러너 전 구간이 올바르게 동작하는지 검증한다. 실 키가 오면
`python -m app.cli collect --source-id <id> --service-key <키>`로 마지막 확인만 하면 된다.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from unittest import mock

import pytest
from sqlalchemy import delete, select

from app.collector.adapters.openapi import fetch_openapi_items
from app.collector.mapper import map_item
from app.collector.runner import run_source
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

    items = fetch_openapi_items(config, "test-service-key", lookback_days=3)

    assert items == SAMPLE_ITEMS
    call_args = mock_fetch.call_args
    assert call_args.args[0] == config["endpoint"]
    sent_params = call_args.kwargs["params"]
    assert sent_params["ServiceKey"] == "test-service-key"
    assert "inqryBgnDt" in sent_params and "inqryEndDt" in sent_params


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
