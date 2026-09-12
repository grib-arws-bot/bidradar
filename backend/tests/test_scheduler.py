"""app/scheduler.py 검증 — source.schedule_times("HH:MM" 최대 3개, 2026-09-05 설정 UI만
도입됐던 값)를 실제로 그 시각에 수집을 트리거하는 실행 엔진(2026-09-10 신규)."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from sqlalchemy import delete, insert

from app.collector.runner import CollectionInProgressError
from app.db import engine
from app.models import source
from app.scheduler import KST, _due_sources, run_due_sources, run_pending_backlog


def _make_temp_source(conn, *, name: str, schedule_times: list[str], active: bool = True) -> int:
    """실제 운영 소스를 건드리지 않는 격리된 임시 소스(2026-09-08 사고 재발 방지 패턴)."""
    return conn.execute(
        insert(source)
        .values(
            name=name, org_name="테스트기관", channel_name="테스트기관",
            base_url="https://apis.data.go.kr/test/scheduler", stage="입찰공고",
            adapter_type="openapi", frequency_minutes=1440, is_system=False, skip_l1=True, active=active,
            legal_tier="A", auto_extract=False, auto_analyze=False, schedule_times=schedule_times,
        )
        .returning(source.c.id)
    ).scalar_one()


def test_due_sources_matches_only_sources_with_that_exact_hhmm():
    now_kst = datetime(2026, 9, 10, 9, 0, tzinfo=KST)
    ids = []
    try:
        with engine.begin() as conn:
            due_id = _make_temp_source(conn, name="_테스트_스케줄_09시", schedule_times=["09:00"])
            other_time_id = _make_temp_source(conn, name="_테스트_스케줄_13시", schedule_times=["13:00"])
            no_schedule_id = _make_temp_source(conn, name="_테스트_스케줄_없음", schedule_times=[])
            inactive_id = _make_temp_source(conn, name="_테스트_스케줄_비활성", schedule_times=["09:00"], active=False)
            ids = [due_id, other_time_id, no_schedule_id, inactive_id]

        due = _due_sources(now_kst)
        due_ids = {sid for sid, _name in due}
        assert due_id in due_ids
        assert other_time_id not in due_ids
        assert no_schedule_id not in due_ids
        assert inactive_id not in due_ids
    finally:
        with engine.begin() as conn:
            conn.execute(delete(source).where(source.c.id.in_(ids)))


def test_due_sources_converts_naive_or_other_tz_now_to_kst():
    # UTC 09:00은 KST(UTC+9)로 18:00 — schedule_times가 "18:00"인 소스만 걸려야 함.
    now_utc = datetime(2026, 9, 10, 9, 0, tzinfo=ZoneInfo("UTC"))
    ids = []
    try:
        with engine.begin() as conn:
            kst_match_id = _make_temp_source(conn, name="_테스트_KST변환_18시", schedule_times=["18:00"])
            utc_literal_id = _make_temp_source(conn, name="_테스트_KST변환_09시", schedule_times=["09:00"])
            ids = [kst_match_id, utc_literal_id]

        due_ids = {sid for sid, _name in _due_sources(now_utc.astimezone(KST))}
        assert kst_match_id in due_ids
        assert utc_literal_id not in due_ids
    finally:
        with engine.begin() as conn:
            conn.execute(delete(source).where(source.c.id.in_(ids)))


def test_run_due_sources_triggers_only_due_sources_and_continues_past_failures():
    now_kst = datetime(2026, 9, 10, 9, 0, tzinfo=KST)
    ids = []
    try:
        with engine.begin() as conn:
            ok_id = _make_temp_source(conn, name="_테스트_실행_정상", schedule_times=["09:00"])
            already_running_id = _make_temp_source(conn, name="_테스트_실행_이미진행중", schedule_times=["09:00"])
            failing_id = _make_temp_source(conn, name="_테스트_실행_예외", schedule_times=["09:00"])
            not_due_id = _make_temp_source(conn, name="_테스트_실행_다른시각", schedule_times=["13:00"])
            ids = [ok_id, already_running_id, failing_id, not_due_id]

        def fake_run(source_id: int):
            if source_id == already_running_id:
                raise CollectionInProgressError("이미 진행 중")
            if source_id == failing_id:
                raise RuntimeError("가짜 실패")
            return {"fetched": 1, "inserted": 1}

        with mock.patch("app.scheduler.run_source_and_process_pending", side_effect=fake_run) as mock_run:
            attempted = run_due_sources(now_kst)

        assert set(attempted) == {ok_id, already_running_id, failing_id}
        assert mock_run.call_count == 3
    finally:
        with engine.begin() as conn:
            conn.execute(delete(source).where(source.c.id.in_(ids)))


def test_run_pending_backlog_returns_counts_from_run_pending_analysis():
    fake_result = {"extraction_candidates": 2, "auto_extracted": 2, "analyze_candidates": 8, "auto_analyzed": 8}
    with mock.patch("app.scheduler.run_pending_analysis", return_value=fake_result) as mock_run:
        result = run_pending_backlog()
    mock_run.assert_called_once_with()
    assert result == fake_result


def test_run_pending_backlog_does_not_raise_when_run_pending_analysis_fails():
    # run_due_sources(매 분)와 별개 잡이라 이번 회차 실패가 스케줄러 자체를 죽이면 안 됨.
    with mock.patch("app.scheduler.run_pending_analysis", side_effect=RuntimeError("가짜 실패")):
        result = run_pending_backlog()
    assert result == {"extraction_candidates": 0, "auto_extracted": 0, "analyze_candidates": 0, "auto_analyzed": 0}
