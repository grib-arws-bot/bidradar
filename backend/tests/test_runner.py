"""U11 러너(run_source) 통합 검증 — 어댑터·매퍼·스코어러 단위 테스트는 test_collector.py에
있음(500줄 상한 초과로 분리, 2026-09-02). 실제 라이브 호출은 공공데이터포털 인증키가 있어야
하므로, 여기서는 url_guard.fetch를 목으로 대체해 어댑터~러너 전 구간이 올바르게 동작하는지
검증한다.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from sqlalchemy import delete, insert, select

from app.collector.runner import run_source
from app.db import engine
from app.models import notice, notice_score, org, raw_payload, source, source_config, source_field_map, source_run

# 2026-09-04 — 날짜를 고정 문자열이 아니라 "지금부터 며칠"로 계산한다. 예전엔 하드코딩된
# 2026-09-01 등을 썼는데 시간이 지나 오늘 날짜가 그 값을 지나가버리면 out_of_window로 걸러져
# 테스트가 깨졌다(2026-09-04 발견). 포맷도 실제 API 응답과 같은 "%Y-%m-%d %H:%M:%S"로 맞춘다 —
# 예전 포맷("%Y%m%d%H%M")은 seed_constants.py의 실제 버그였던 값이라 지금은 seed에 없다.
_NOW = datetime.now(timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


SAMPLE_ITEMS = [
    {
        "bidNtceNo": "R26TEST0001",
        "bidNtceNm": "지능형 CCTV 통합관제시스템 구축",
        "ntceInsttNm": "테스트발주기관",
        "bidNtceDt": _fmt(_NOW - timedelta(days=1)),
        "bidClseDt": _fmt(_NOW + timedelta(days=19)),
        "presmptPrce": "512,000,000",
        "bidNtceDtlUrl": "https://www.g2b.go.kr/bid/R26TEST0001",
    },
    {
        "bidNtceNo": "R26TEST0002",
        "bidNtceNm": "청사 화장실 리모델링",
        "ntceInsttNm": "테스트발주기관",
        "bidNtceDt": _fmt(_NOW),
        "bidClseDt": _fmt(_NOW + timedelta(days=20)),
        "presmptPrce": "80,000,000",
        "bidNtceDtlUrl": "https://www.g2b.go.kr/bid/R26TEST0002",
    },
]


def _paginated_mock_fetch(items: list[dict]) -> mock.Mock:
    # 2026-09-04 — 이 소스(나라장터 입찰공고정보서비스)의 실제 config에 pagination이 추가되면서
    # (60일 초과 시 API 자체가 범위 초과 에러를 내고, 페이지당 100건 고정이라 여러 페이지를
    # 넘겨야 전량이 나옴) 고정 mock.Mock(return_value=...)을 쓰면 매번 같은 2건을 계속 돌려줘
    # 빈 페이지를 못 만나 max_pages(50)까지 다 돈다(100건 fetched로 테스트가 깨짐). pageNo=1일
    # 때만 실제 항목을, 그 외(2페이지째)엔 빈 목록을 돌려줘 정상적으로 1페이지에서 멈추게 한다.
    def _side_effect(*args, **kwargs):
        page = kwargs.get("params", {}).get("pageNo", "1")
        resp = mock.Mock()
        resp.json.return_value = {"response": {"body": {"items": items if page == "1" else []}}}
        return resp

    return mock.Mock(side_effect=_side_effect)


def _bid_service_source_id() -> int:
    with engine.connect() as conn:
        row = conn.execute(select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")).first()
    assert row, "U2 시드가 먼저 실행돼 있어야 함"
    return row[0]


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
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", _paginated_mock_fetch(SAMPLE_ITEMS))

    source_id = _bid_service_source_id()
    with engine.begin() as conn:
        result = run_source(conn, source_id)

    assert result == {"fetched": 2, "inserted": 2, "skipped": 0, "scored": 1, "out_of_window": 0}

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
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", _paginated_mock_fetch(SAMPLE_ITEMS))

    source_id = _bid_service_source_id()
    with engine.begin() as conn:
        run_source(conn, source_id)
        second = run_source(conn, source_id)

    # 같은 url(공고)이 이미 있으면 새로 insert하지 않는다 — "inserted" 0.
    assert second["inserted"] == 0
    assert second["fetched"] == 2


def test_run_source_second_call_narrows_window_to_last_success(monkeypatch):
    mock_fetch = _paginated_mock_fetch(SAMPLE_ITEMS)
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


# ---- 법적 등급 강제(advisory INBOX #5, 2026-09-01) ------------------------------------


_TITLE_ONLY_FIELD_MAP = [("title", "$.title", None)]


def _make_temp_source(
    conn, *, legal_tier: str, frequency_minutes: int = 1440, field_maps: list[tuple] = _TITLE_ONLY_FIELD_MAP
) -> int:
    """C/B등급 강제를 검증하려고 만드는 테스트 전용 소스 — 시드 데이터(IRIS 등)를 건드리지
    않고 격리해서 확인한다."""
    src_id = conn.execute(
        insert(source)
        .values(
            name=f"테스트 소스({legal_tier}등급)", org_name="테스트기관", base_url="https://example.grib-test.kr/api",
            stage="입찰공고", adapter_type="openapi", frequency_minutes=frequency_minutes,
            is_system=False, skip_l1=True, active=True, legal_tier=legal_tier,
        )
        .returning(source.c.id)
    ).scalar_one()
    cfg_id = conn.execute(
        insert(source_config)
        .values(source_id=src_id, ver=1, config={"endpoint": "https://example.grib-test.kr/api", "items_path": "$.items[*]"})
        .returning(source_config.c.id)
    ).scalar_one()
    for target_field, path, format_hint in field_maps:
        conn.execute(
            insert(source_field_map).values(
                source_config_id=cfg_id, target_field=target_field, source_path=path, format_hint=format_hint
            )
        )
    return src_id


def test_run_source_blocks_legal_tier_c():
    with engine.begin() as conn:
        source_id = _make_temp_source(conn, legal_tier="C")
        try:
            with pytest.raises(ValueError, match="법적 등급 C"):
                run_source(conn, source_id)
        finally:
            conn.execute(delete(source).where(source.c.id == source_id))


def test_run_source_enforces_tier_b_minimum_interval(monkeypatch):
    mock_response = mock.Mock()
    mock_response.json.return_value = {"items": [{"title": "t"}]}
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock.Mock(return_value=mock_response))

    # 각 단계를 별도 트랜잭션으로 커밋한다 — run_source의 _record_run이 호출부와 독립된
    # 커넥션으로 source_run을 쓰기 때문에(CLAUDE.md 취지: 실패도 반드시 기록), 같은 트랜잭션
    # 안에서 소스를 만들고 바로 run_source를 부르면 그 커넥션 눈엔 소스가 아직 안 보여
    # FK 위반이 난다.
    with engine.begin() as conn:
        source_id = _make_temp_source(conn, legal_tier="B", frequency_minutes=1440)
    try:
        with engine.begin() as conn:
            conn.execute(
                insert(source_run).values(
                    source_id=source_id, status="ok", items_fetched=0,
                    run_at=datetime.now(timezone.utc) - timedelta(minutes=5),
                )
            )
        with engine.begin() as conn:
            with pytest.raises(ValueError, match="최소 수집 간격"):
                run_source(conn, source_id)
        # force=True는 관리자 수동 재수집용 우회 — 이건 통과해야 함
        with engine.begin() as conn:
            run_source(conn, source_id, force=True)
    finally:
        with engine.begin() as conn:
            conn.execute(delete(source_run).where(source_run.c.source_id == source_id))
            conn.execute(delete(raw_payload).where(raw_payload.c.source_id == source_id))
            conn.execute(delete(source).where(source.c.id == source_id))


# ---- 날짜범위 파라미터 없는 API의 클라이언트측 기간 필터(2026-09-02, IRIS 재수집 정확도) --


def test_run_source_filters_items_older_than_collection_window(monkeypatch):
    old_dt = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y%m%d%H%M")
    recent_dt = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y%m%d%H%M")
    mock_response = mock.Mock()
    mock_response.json.return_value = {
        "items": [
            {"title": "오래된 공고", "org": "테스트발주기관_기간필터", "openDate": old_dt, "url": "https://x/old"},
            {"title": "최근 공고", "org": "테스트발주기관_기간필터", "openDate": recent_dt, "url": "https://x/recent"},
        ]
    }
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock.Mock(return_value=mock_response))

    field_maps = [
        ("title", "$.title", None), ("org_name", "$.org", None),
        ("open_dt", "$.openDate", "%Y%m%d%H%M"), ("url", "$.url", None),
    ]
    with engine.begin() as conn:
        source_id = _make_temp_source(conn, legal_tier="A", field_maps=field_maps)
    try:
        with engine.begin() as conn:
            # 이력이 없어 기본 60일 캡이 적용됨 — 90일 전 공고는 제외, 10일 전 공고만 남아야 함
            result = run_source(conn, source_id, max_lookback_days=60)
    finally:
        with engine.begin() as conn:
            conn.execute(delete(notice).where(notice.c.source_id == source_id))
            conn.execute(delete(org).where(org.c.name == "테스트발주기관_기간필터"))
            conn.execute(delete(raw_payload).where(raw_payload.c.source_id == source_id))
            conn.execute(delete(source_run).where(source_run.c.source_id == source_id))
            conn.execute(delete(source).where(source.c.id == source_id))

    assert result == {"fetched": 2, "inserted": 1, "skipped": 0, "scored": 0, "out_of_window": 1}


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
