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
from app.models import customer, source
from app.scheduler import (
    KST,
    _due_customers,
    _due_sources,
    run_due_customer_emails,
    run_due_sources,
    run_pending_backlog,
)


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

        # 2026-09-15 — 데모 시드가 실제 운영 소스 5개에도 schedule_times=["09:00"]을 채우면서
        # (app/seed_data.py _seed_schedule_times) 같은 09:00에 이 테스트가 만든 소스 말고도
        # 다른 소스가 "이번 분에 예정됨"으로 같이 걸릴 수 있게 됐다 — 이 테스트의 관심사는
        # "이 3개는 반드시 시도됐고 13:00짜리는 절대 안 걸렸다"이지 "이 3개만 유일하게 걸렸다"가
        # 아니므로 부분집합 검사로 바꾼다(다른 소스 유무에 흔들리지 않게).
        assert {ok_id, already_running_id, failing_id} <= set(attempted)
        assert not_due_id not in set(attempted)
        assert mock_run.call_count >= 3
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


# ---- 고객 보고서 메일 자동발송(2026-09-14 도입, 2026-09-15 (요일,시각) 쌍으로 재설계) -----


def _make_temp_customer(conn, *, name: str, schedule: list[dict] | None = None, active: bool = True) -> int:
    return conn.execute(
        insert(customer)
        .values(name=name, plan_tier="standard", active=active, report_auto_send_schedule=schedule or [])
        .returning(customer.c.id)
    ).scalar_one()


def test_due_customers_matches_only_day_and_time():
    # 월요일(2026-09-14는 실제 월요일) 09:00 기준 — 요일+시각이 정확히 맞는 고객만 걸려야 함.
    now_kst = datetime(2026, 9, 14, 9, 0, tzinfo=KST)
    ids = []
    try:
        with engine.begin() as conn:
            due_id = _make_temp_customer(
                conn, name="_테스트_고객_월요일9시",
                schedule=[{"day": 1, "time": "09:00"}, {"day": 3, "time": "09:00"}, {"day": 5, "time": "09:00"}],
            )
            other_day_id = _make_temp_customer(
                conn, name="_테스트_고객_화요일만", schedule=[{"day": 2, "time": "09:00"}]
            )
            other_time_id = _make_temp_customer(
                conn, name="_테스트_고객_다른시각", schedule=[{"day": 1, "time": "18:00"}]
            )
            no_schedule_id = _make_temp_customer(conn, name="_테스트_고객_미설정", schedule=[])
            inactive_id = _make_temp_customer(
                conn, name="_테스트_고객_비활성", schedule=[{"day": 1, "time": "09:00"}], active=False
            )
            # 2026-09-15 — 이 쌍 재설계의 핵심 케이스: "월 07시·목 20시"처럼 요일마다 다른
            # 시각을 지정해도 월 09시엔 안 걸려야 한다(예전 카르테시안 곱 방식이었다면 걸렸음).
            mismatched_pair_id = _make_temp_customer(
                conn, name="_테스트_고객_요일시각_안맞음",
                schedule=[{"day": 1, "time": "07:00"}, {"day": 4, "time": "09:00"}],
            )
            ids = [due_id, other_day_id, other_time_id, no_schedule_id, inactive_id, mismatched_pair_id]

        due_ids = {cid for cid, _name in _due_customers(now_kst)}
        assert due_id in due_ids
        assert other_day_id not in due_ids
        assert other_time_id not in due_ids
        assert mismatched_pair_id not in due_ids
        assert no_schedule_id not in due_ids
        assert inactive_id not in due_ids
    finally:
        with engine.begin() as conn:
            conn.execute(delete(customer).where(customer.c.id.in_(ids)))


def test_due_customers_matches_when_day_stored_as_string():
    """2026-09-16 발견 회귀 테스트 — e2f3a4b5c6d7 마이그레이션이 jsonb_array_elements_text()로
    기존 요일 값을 옮기면서 day를 JSON 문자열("3")로 저장했다. _due_customers()가 정수
    isoweekday()와 `==`로 직접 비교했다면 "3" == 3이 항상 False라 이 재설계가 나온
    2026-09-15부터 발견 시점(2026-09-16)까지 자동발송이 단 한 건도 실행되지 못했다 — 실제
    prod의 고객 4명 전원이 이 상태였다. 이 테스트는 그 정확한 데이터 모양(문자열 day)을
    재현해 _due_customers()가 int() 캐스팅으로 여전히 정상 매칭하는지 검증한다."""
    now_kst = datetime(2026, 9, 14, 9, 0, tzinfo=KST)  # 2026-09-14는 실제 월요일
    ids = []
    try:
        with engine.begin() as conn:
            string_day_id = _make_temp_customer(
                conn, name="_테스트_고객_문자열요일",
                schedule=[{"day": "1", "time": "09:00"}],  # 마이그레이션 버그가 만든 실제 모양
            )
            ids = [string_day_id]

        due_ids = {cid for cid, _name in _due_customers(now_kst)}
        assert string_day_id in due_ids
    finally:
        with engine.begin() as conn:
            conn.execute(delete(customer).where(customer.c.id.in_(ids)))


def test_run_due_customer_emails_generates_and_sends_then_skips_zero_matches(monkeypatch):
    now_kst = datetime(2026, 9, 14, 9, 0, tzinfo=KST)
    monkeypatch.setattr("app.scheduler.time.sleep", lambda _seconds: None)  # 테스트 속도
    ids = []
    try:
        with engine.begin() as conn:
            has_matches_id = _make_temp_customer(conn, name="_테스트_고객_발송대상", schedule=[{"day": 1, "time": "09:00"}])
            zero_matches_id = _make_temp_customer(conn, name="_테스트_고객_0건", schedule=[{"day": 1, "time": "09:00"}])
            ids = [has_matches_id, zero_matches_id]

        def fake_generate(customer_id: int):
            total = 3 if customer_id == has_matches_id else 0
            return {"id": 555, "customer_id": customer_id, "summary": {"total": total}}

        with mock.patch("app.scheduler.generate_report", side_effect=fake_generate) as mock_generate, \
             mock.patch("app.scheduler.send_report_email") as mock_send:
            sent = run_due_customer_emails(now_kst)

        assert set(sent) == {has_matches_id}
        assert mock_generate.call_count == 2
        mock_send.assert_called_once()
        assert mock_send.call_args.args[1] == has_matches_id
        assert mock_send.call_args.args[2] == 555
    finally:
        with engine.begin() as conn:
            conn.execute(delete(customer).where(customer.c.id.in_(ids)))


def test_run_due_customer_emails_skips_when_no_interest_profile(monkeypatch):
    # generate_report()는 관심주제가 아예 설정 안 된 고객에겐 None을 돌려준다(interest_report.py).
    now_kst = datetime(2026, 9, 14, 9, 0, tzinfo=KST)
    ids = []
    try:
        with engine.begin() as conn:
            no_profile_id = _make_temp_customer(conn, name="_테스트_고객_관심주제없음", schedule=[{"day": 1, "time": "09:00"}])
            ids = [no_profile_id]

        with mock.patch("app.scheduler.generate_report", return_value=None), \
             mock.patch("app.scheduler.send_report_email") as mock_send:
            sent = run_due_customer_emails(now_kst)

        assert no_profile_id not in sent
        mock_send.assert_not_called()
    finally:
        with engine.begin() as conn:
            conn.execute(delete(customer).where(customer.c.id.in_(ids)))


def test_run_due_customer_emails_continues_past_one_customer_failure(monkeypatch):
    now_kst = datetime(2026, 9, 14, 9, 0, tzinfo=KST)
    monkeypatch.setattr("app.scheduler.time.sleep", lambda _seconds: None)
    ids = []
    try:
        with engine.begin() as conn:
            failing_id = _make_temp_customer(conn, name="_테스트_고객_예외", schedule=[{"day": 1, "time": "09:00"}])
            ok_id = _make_temp_customer(conn, name="_테스트_고객_정상", schedule=[{"day": 1, "time": "09:00"}])
            ids = [failing_id, ok_id]

        def fake_generate(customer_id: int):
            if customer_id == failing_id:
                raise RuntimeError("가짜 실패")
            return {"id": 1, "customer_id": customer_id, "summary": {"total": 1}}

        with mock.patch("app.scheduler.generate_report", side_effect=fake_generate), \
             mock.patch("app.scheduler.send_report_email") as mock_send:
            sent = run_due_customer_emails(now_kst)

        assert sent == [ok_id]  # failing_id는 예외를 삼키고 건너뛰되 ok_id는 계속 처리됨
        mock_send.assert_called_once()
    finally:
        with engine.begin() as conn:
            conn.execute(delete(customer).where(customer.c.id.in_(ids)))
