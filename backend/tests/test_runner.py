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
from sqlalchemy import delete, func, insert, select

from app.collector.runner import CollectionInProgressError, run_source
from app.collector.scorer import L2_PROMOTE_THRESHOLD
from app.db import engine
from app.models import (
    analysis, notice, notice_score, org, raw_payload, source, source_config, source_field_map, source_run,
)

# run_source()가 매 수집 직후 notice_dedup.find_and_mark_superseded를 자동 호출하게 되면서
# (2026-09-06) 반환값에 dedup_* 키가 추가됨 — 실제 공유 DB 전체를 재계산한 결과라 값을
# 하드코딩할 수 없으므로, 기존 고정 필드 비교에서는 이 키들만 떼어내고 별도로 타입만 확인한다.
_DEDUP_RESULT_KEYS = {"dedup_groups_with_duplicates", "dedup_notices_updated"}
# 이번 실행에서 새로 들어온 공고 id 목록(2026-09-07, run_source_and_process_pending이 소비) —
# 값 자체가 테스트마다 다른 id라 정확히 비교할 수 없어 타입(list[int])만 확인한다.
_NOTICE_IDS_KEY = "inserted_notice_ids"
# notice_id -> 원본 API 항목(2026-09-08, g2b 첨부분석 재조회 없애는 데 씀) — 마찬가지로
# 내용을 정확히 비교할 수 없어 타입(dict)만 확인한다.
_RAW_ITEMS_KEY = "inserted_raw_items"


def _assert_run_result(result: dict, expected: dict) -> None:
    dedup_part = {k: result[k] for k in _DEDUP_RESULT_KEYS}
    assert all(isinstance(v, int) and v >= 0 for v in dedup_part.values())
    assert isinstance(result[_NOTICE_IDS_KEY], list) and all(isinstance(i, int) for i in result[_NOTICE_IDS_KEY])
    assert isinstance(result[_RAW_ITEMS_KEY], dict)
    ignored_keys = _DEDUP_RESULT_KEYS | {_NOTICE_IDS_KEY, _RAW_ITEMS_KEY}
    assert {k: v for k, v in result.items() if k not in ignored_keys} == expected

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
    # 2026-09-05부터 run_source()는 목록 수집만 한다(A1/A2는 app/services/pending_analysis.py로
    # 분리) — 이 소스의 auto_extract 설정과 완전히 무관해졌으므로 더 이상 손댈 필요 없음.
    source_id = _bid_service_source_id()
    yield
    with engine.begin() as conn:
        test_notice_ids = [
            row[0]
            for row in conn.execute(select(notice.c.id).where(notice.c.notice_no.in_(["R26TEST0001", "R26TEST0002"])))
        ]
        if test_notice_ids:
            conn.execute(delete(notice_score).where(notice_score.c.notice_id.in_(test_notice_ids)))
            conn.execute(delete(analysis).where(analysis.c.notice_id.in_(test_notice_ids)))
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

    _assert_run_result(result, {"fetched": 2, "inserted": 2, "skipped": 0, "scored": 1, "out_of_window": 0, "already_closed": 0})

    with engine.connect() as conn:
        cctv_notice = conn.execute(select(notice.c.id, notice.c.title).where(notice.c.notice_no == "R26TEST0001")).first()
        assert cctv_notice is not None
        scores = conn.execute(select(notice_score.c.l2_score).where(notice_score.c.notice_id == cctv_notice[0])).all()
        assert len(scores) == 1
        # 정확한 점수는 관리자가 키워드를 추가/삭제하면 달라질 수 있다(2026-09-05, 키워드
        # 관리 CRUD 신설) — 승급 문턱을 넘는지만 검증한다.
        assert scores[0][0] >= L2_PROMOTE_THRESHOLD

        run_row = conn.execute(
            select(source_run.c.status, source_run.c.items_fetched).where(source_run.c.source_id == source_id).order_by(source_run.c.id.desc())
        ).first()
        assert run_row == ("ok", 2)


def test_run_source_returns_raw_item_per_inserted_notice(monkeypatch):
    # 2026-09-08 — process_new_notices가 첨부분석 시 목록 API를 다시 재조회하지 않도록,
    # 방금 수집한 원본 API 항목을 notice_id별로 그대로 돌려줘야 한다.
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", _paginated_mock_fetch(SAMPLE_ITEMS))

    source_id = _bid_service_source_id()
    with engine.begin() as conn:
        result = run_source(conn, source_id)
        cctv_notice_id = conn.execute(
            select(notice.c.id).where(notice.c.notice_no == "R26TEST0001")
        ).scalar_one()

    raw_items = result["inserted_raw_items"]
    assert set(raw_items.keys()) == set(result["inserted_notice_ids"])
    assert raw_items[cctv_notice_id]["bidNtceNo"] == "R26TEST0001"


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


def test_run_source_explicit_window_bypasses_auto_narrowing(monkeypatch):
    """window= 를 주면 직전 성공 이력과 무관하게 그 구간을 그대로 써야 한다(2026-09-05,
    나라장터 입찰공고 30일 백필을 하루씩 쪼갤 때 쓰는 경로)."""
    mock_fetch = _paginated_mock_fetch(SAMPLE_ITEMS)
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock_fetch)

    source_id = _bid_service_source_id()
    with engine.begin() as conn:
        run_source(conn, source_id)  # 성공 이력을 하나 만들어 둔다 — 자동 좁히기가 있다면 걸릴 상황

    explicit_begin = datetime.now(timezone.utc) - timedelta(days=20)
    explicit_end = datetime.now(timezone.utc) - timedelta(days=19)
    with engine.begin() as conn:
        run_source(conn, source_id, window=(explicit_begin, explicit_end))

    sent_params = mock_fetch.call_args.kwargs["params"]
    assert sent_params["inqryBgnDt"] == explicit_begin.strftime("%Y%m%d%H%M")
    assert sent_params["inqryEndDt"] == explicit_end.strftime("%Y%m%d%H%M")


# ---- 법적 등급 강제(advisory INBOX #5, 2026-09-01) ------------------------------------


_TITLE_ONLY_FIELD_MAP = [("title", "$.title", None)]


def _make_temp_source(
    conn, *, legal_tier: str, frequency_minutes: int = 1440, field_maps: list[tuple] = _TITLE_ONLY_FIELD_MAP,
    auto_extract: bool = False,
) -> int:
    """C/B등급 강제를 검증하려고 만드는 테스트 전용 소스 — 시드 데이터(IRIS 등)를 건드리지
    않고 격리해서 확인한다."""
    src_id = conn.execute(
        insert(source)
        .values(
            name=f"테스트 소스({legal_tier}등급)", org_name="테스트기관", channel_name="테스트기관",
            base_url="https://example.grib-test.kr/api",
            stage="입찰공고", adapter_type="openapi", frequency_minutes=frequency_minutes,
            is_system=False, skip_l1=True, active=True, legal_tier=legal_tier, auto_extract=auto_extract,
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


# 법적 등급 B 소스의 "최소 수집 간격" 강제는 사용자 지시로 제거했다(2026-09-11, 의사결정_로그
# 104번) — 스케줄대로 항상 수집돼야 한다는 운영 요구가 advisory INBOX #5의 간격 제약보다
# 우선한다고 판단. 등급 C(수집 금지) 차단은 그대로 유지된다(위 test_run_source_blocks_legal_tier_c).


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

    _assert_run_result(result, {"fetched": 2, "inserted": 1, "skipped": 0, "scored": 0, "out_of_window": 1, "already_closed": 0})


# ---- 이미 마감된 공고는 수집 단계에서 제외(2026-09-04, 나라장터 82% 마감건 혼입 발견) -------


def test_run_source_skips_items_already_past_close_date(monkeypatch):
    now = datetime.now(timezone.utc)
    mock_response = mock.Mock()
    mock_response.json.return_value = {
        "items": [
            {
                "title": "이미 마감된 공고", "org": "테스트발주기관_마감필터",
                "openDate": (now - timedelta(days=5)).strftime("%Y%m%d%H%M"),
                "closeDate": (now - timedelta(days=1)).strftime("%Y%m%d%H%M"),
                "url": "https://x/closed",
            },
            {
                "title": "아직 진행중인 공고", "org": "테스트발주기관_마감필터",
                "openDate": (now - timedelta(days=5)).strftime("%Y%m%d%H%M"),
                "closeDate": (now + timedelta(days=5)).strftime("%Y%m%d%H%M"),
                "url": "https://x/open",
            },
            {
                # close_dt 자체가 없는 소스(IRIS 등)는 "마감됐다"고 판단할 근거가 없어 대상 제외
                "title": "마감일 없는 공고", "org": "테스트발주기관_마감필터",
                "openDate": (now - timedelta(days=5)).strftime("%Y%m%d%H%M"),
                "url": "https://x/no-close",
            },
        ]
    }
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", mock.Mock(return_value=mock_response))

    field_maps = [
        ("title", "$.title", None), ("org_name", "$.org", None),
        ("open_dt", "$.openDate", "%Y%m%d%H%M"), ("close_dt", "$.closeDate", "%Y%m%d%H%M"),
        ("url", "$.url", None),
    ]
    with engine.begin() as conn:
        source_id = _make_temp_source(conn, legal_tier="A", field_maps=field_maps)
    try:
        with engine.begin() as conn:
            result = run_source(conn, source_id, max_lookback_days=60)

        with engine.connect() as conn:
            titles = {
                row.title
                for row in conn.execute(select(notice.c.title).where(notice.c.source_id == source_id))
            }
    finally:
        with engine.begin() as conn:
            conn.execute(delete(notice).where(notice.c.source_id == source_id))
            conn.execute(delete(org).where(org.c.name == "테스트발주기관_마감필터"))
            conn.execute(delete(raw_payload).where(raw_payload.c.source_id == source_id))
            conn.execute(delete(source_run).where(source_run.c.source_id == source_id))
            conn.execute(delete(source).where(source.c.id == source_id))

    _assert_run_result(result, {"fetched": 3, "inserted": 2, "skipped": 0, "scored": 0, "out_of_window": 0, "already_closed": 1})
    assert titles == {"아직 진행중인 공고", "마감일 없는 공고"}


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


# 첨부문서 자동 추출(A1)·AI 자동분석(A2) 트리거 검증은 test_pending_analysis.py로 옮겼다
# (2026-09-05, run_source에서 분리 — app/services/pending_analysis.py 참고).


def test_run_source_and_process_pending_chains_and_merges_results(monkeypatch):
    """파이프라인 전체(수집→중복체크→첨부분석→AI분석) 연결 검증(2026-09-07) — run_source와
    process_new_notices 자체 동작은 각각 다른 테스트가 이미 검증하므로, 여기선 두 호출이
    실제로 순서대로 이어지고(이번에 새로 수집된 공고 id만 다음 단계로 넘어감) 결과가 하나로
    합쳐지는지만 목으로 확인한다."""
    from app.collector import runner

    raw_items = {555: {"bidNtceNo": "TEST"}}
    collect_result = {
        "fetched": 3, "inserted": 1, "skipped": 0, "scored": 1, "out_of_window": 0, "already_closed": 2,
        "dedup_groups_with_duplicates": 0, "dedup_notices_updated": 0, "inserted_notice_ids": [555],
        "inserted_raw_items": raw_items,
    }
    pending_result = {"extraction_candidates": 1, "auto_extracted": 1, "analyze_candidates": 0, "auto_analyzed": 0}

    # 2026-09-08 — 'running' 행 시작/마감(_start_run·_finish_run)과 중복실행 거부
    # (_reject_if_already_running)는 이 테스트의 관심사(오케스트레이션 순서·결과 병합)가
    # 아니라 목으로 대체한다. source_id=999는 실제 소스가 아니라 source_run에 진짜로 쓰면
    # FK 위반이 난다.
    with mock.patch.object(runner, "run_source", return_value=collect_result) as mock_collect, \
         mock.patch.object(runner, "process_new_notices", return_value=pending_result) as mock_pending, \
         mock.patch.object(runner, "_reject_if_already_running") as mock_reject, \
         mock.patch.object(runner, "_start_run", return_value=4242) as mock_start, \
         mock.patch.object(runner, "_finish_run") as mock_finish:
        result = runner.run_source_and_process_pending(999)

    mock_reject.assert_called_once_with(999)
    mock_start.assert_called_once_with(999)
    mock_collect.assert_called_once()
    assert mock_collect.call_args.args[1] == 999
    assert mock_collect.call_args.kwargs["run_id"] == 4242
    mock_pending.assert_called_once_with(999, [555], raw_items_by_notice_id=raw_items)
    mock_finish.assert_called_once_with(4242, status="ok", items_fetched=3)
    # 내부 처리용 — 최종 결과엔 노출 안 함
    assert "inserted_notice_ids" not in result
    assert "inserted_raw_items" not in result
    assert result == {**collect_result, **pending_result}


# ---- "지금 수집" 중복 실행 방지 + 진행 중 표시(2026-09-08, 사용자 발견 — 클릭 후 다른
# 메뉴로 갔다 돌아오면 이미 끝난 것처럼 보이던 문제) ----------------------------------------


def test_run_source_and_process_pending_rejects_when_already_running(monkeypatch):
    from app.collector import runner

    source_id = _bid_service_source_id()
    with engine.begin() as conn:
        run_id = conn.execute(
            insert(source_run).values(source_id=source_id, status="running", items_fetched=0).returning(source_run.c.id)
        ).scalar_one()

    try:
        with mock.patch.object(runner, "run_source") as mock_collect:
            with pytest.raises(CollectionInProgressError):
                runner.run_source_and_process_pending(source_id)
        mock_collect.assert_not_called()  # 거부됐으면 실제 수집 자체가 시도되면 안 됨
    finally:
        with engine.begin() as conn:
            conn.execute(delete(source_run).where(source_run.c.id == run_id))


def test_run_source_and_process_pending_allows_after_stale_running_row(monkeypatch):
    # RUNNING_STALE_MINUTES를 넘긴 'running' 행은 죽은 프로세스로 보고 실패 마감한 뒤 새
    # 시도를 허용해야 한다 — 안 그러면 서버가 한 번 죽었을 때 그 소스가 영원히 잠긴다.
    from app.collector import runner

    source_id = _bid_service_source_id()
    stale_at = datetime.now(timezone.utc) - timedelta(minutes=runner.RUNNING_STALE_MINUTES + 5)
    with engine.begin() as conn:
        stale_run_id = conn.execute(
            insert(source_run)
            .values(source_id=source_id, status="running", items_fetched=0, run_at=stale_at)
            .returning(source_run.c.id)
        ).scalar_one()

    collect_result = {
        "fetched": 0, "inserted": 0, "skipped": 0, "scored": 0, "out_of_window": 0, "already_closed": 0,
        "dedup_groups_with_duplicates": 0, "dedup_notices_updated": 0, "inserted_notice_ids": [], "inserted_raw_items": {},
    }
    pending_result = {"extraction_candidates": 0, "auto_extracted": 0, "analyze_candidates": 0, "auto_analyzed": 0}
    new_run_id = None
    try:
        with mock.patch.object(runner, "run_source", return_value=collect_result), \
             mock.patch.object(runner, "process_new_notices", return_value=pending_result):
            runner.run_source_and_process_pending(source_id)  # 예외 없이 통과해야 함

        with engine.connect() as conn:
            stale_status = conn.execute(select(source_run.c.status).where(source_run.c.id == stale_run_id)).scalar_one()
            new_run_id = conn.execute(
                select(func.max(source_run.c.id)).where(source_run.c.source_id == source_id)
            ).scalar_one()
        assert stale_status == "fail"  # 오래된 running 행은 실패로 마감됨
        assert new_run_id != stale_run_id  # 새 시도는 별도 행
    finally:
        ids_to_delete = [stale_run_id] + ([new_run_id] if new_run_id else [])
        with engine.begin() as conn:
            conn.execute(delete(source_run).where(source_run.c.id.in_(ids_to_delete)))


def test_run_source_and_process_pending_marks_running_then_ok(monkeypatch):
    # 'running' 행이 실제로 남았다가 성공 시 'ok'로 바뀌는지 실제 DB로 확인(위 테스트들은
    # 오케스트레이션·거부 로직만 목으로 봄 — 여기선 run_source 자체는 실행시키되 fetch만 목).
    monkeypatch.setattr("app.collector.adapters.openapi.fetch", _paginated_mock_fetch(SAMPLE_ITEMS))
    from app.collector import runner

    source_id = _bid_service_source_id()
    with mock.patch.object(runner, "process_new_notices", return_value={
        "extraction_candidates": 0, "auto_extracted": 0, "analyze_candidates": 0, "auto_analyzed": 0,
    }):
        runner.run_source_and_process_pending(source_id)

    with engine.connect() as conn:
        run_row = conn.execute(
            select(source_run.c.status, source_run.c.items_fetched)
            .where(source_run.c.source_id == source_id)
            .order_by(source_run.c.id.desc())
            .limit(1)
        ).first()
    assert run_row == ("ok", 2)  # 성공적으로 마감됐고, 중간에 'running'으로 남는 별도 행이 안 생김(같은 행을 갱신)

    with engine.connect() as conn:
        running_count = conn.execute(
            select(func.count()).select_from(source_run).where(source_run.c.source_id == source_id, source_run.c.status == "running")
        ).scalar_one()
    assert running_count == 0  # 끝난 뒤엔 'running' 상태로 남는 행이 없어야 함
