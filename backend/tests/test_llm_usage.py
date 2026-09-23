"""Claude API 사용량 집계(2026-09-12) — app/services/llm_usage.py 검증. 실제 시드/개발 DB에
이미 데이터가 있을 수 있어 정확한 총량 대신 "알고 있는 값을 넣었을 때 그만큼 늘어나는지"
(델타)로 검증한다."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import analysis, customer, newsletter_report, notice, notice_strategy, source
from app.services.llm_usage import get_llm_usage_summary

# 델타 비교 테스트는 "이번 달 누적" 필터(2026-09-12 도입, overview.py의 get_system_overview가
# 실제로는 이번 달 1일 자정을 넘김) 자체를 검증하려는 게 아니라 필드 합산이 맞는지가 목적이라,
# 아주 이른 시각을 넘겨 사실상 필터가 걸리지 않게 한다 — 월말 자정 근처에 테스트가 도는
# 우연으로 흔들리지 않도록.
_ALL_TIME = datetime(2000, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def temp_customer():
    with engine.begin() as conn:
        customer_id = conn.execute(
            insert(customer).values(name="[테스트] LLM 사용량 검증용", plan_tier="standard").returning(customer.c.id)
        ).scalar_one()
    yield customer_id
    with engine.begin() as conn:
        conn.execute(delete(customer).where(customer.c.id == customer_id))


@pytest.fixture
def temp_notice():
    with engine.connect() as conn:
        source_id = conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()
    with engine.begin() as conn:
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] LLM 사용량 검증용 공고",
                url="https://example.grib-test.kr/notice/llm-usage-test",
            ).returning(notice.c.id)
        ).scalar_one()
    yield notice_id
    with engine.begin() as conn:
        conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_llm_usage_includes_a2_structure_calls(temp_notice):
    with engine.begin() as conn:
        before = get_llm_usage_summary(conn, _ALL_TIME)
        analysis_id = conn.execute(
            insert(analysis).values(
                notice_id=temp_notice, source_kind="notice", input_ref="test", step="A2_structure", status="done",
                llm_tokens=1000, llm_cost=0.05,
            ).returning(analysis.c.id)
        ).scalar_one()
        after = get_llm_usage_summary(conn, _ALL_TIME)

    try:
        assert after["breakdown"]["structure"]["calls"] == before["breakdown"]["structure"]["calls"] + 1
        assert after["breakdown"]["structure"]["tokens"] == before["breakdown"]["structure"]["tokens"] + 1000
        assert round(after["breakdown"]["structure"]["cost_usd"] - before["breakdown"]["structure"]["cost_usd"], 4) == 0.05
        assert after["total_calls"] == before["total_calls"] + 1
    finally:
        # analysis.notice_id는 ON DELETE CASCADE가 아니라(analysis_pilot.py·notice_cleanup.py
        # 참고), temp_notice 픽스처가 notice를 지우기 전에 먼저 지워야 FK 위반이 안 난다.
        with engine.begin() as conn:
            conn.execute(delete(analysis).where(analysis.c.id == analysis_id))


def test_llm_usage_includes_customer_profile_summary(temp_customer):
    from datetime import datetime, timezone

    with engine.begin() as conn:
        before = get_llm_usage_summary(conn, _ALL_TIME)
        conn.execute(
            customer.update().where(customer.c.id == temp_customer).values(
                profile_summarized_at=datetime.now(timezone.utc), profile_summary_tokens=2000, profile_summary_cost=0.1
            )
        )
        after = get_llm_usage_summary(conn, _ALL_TIME)

    assert after["breakdown"]["customer_profile"]["calls"] == before["breakdown"]["customer_profile"]["calls"] + 1
    assert after["breakdown"]["customer_profile"]["tokens"] == before["breakdown"]["customer_profile"]["tokens"] + 2000


def test_llm_usage_includes_report_commentary(temp_customer):
    from datetime import datetime, timezone

    with engine.begin() as conn:
        before = get_llm_usage_summary(conn, _ALL_TIME)
        report_id = conn.execute(
            insert(newsletter_report).values(
                customer_id=temp_customer, token="test-llm-usage-token", notices=[], summary={},
                ai_generated_at=datetime.now(timezone.utc), ai_tokens=3000, ai_cost_usd=0.2,
            ).returning(newsletter_report.c.id)
        ).scalar_one()
        after = get_llm_usage_summary(conn, _ALL_TIME)
        conn.execute(delete(newsletter_report).where(newsletter_report.c.id == report_id))

    assert after["breakdown"]["report_commentary"]["calls"] == before["breakdown"]["report_commentary"]["calls"] + 1
    assert after["breakdown"]["report_commentary"]["tokens"] == before["breakdown"]["report_commentary"]["tokens"] + 3000


def test_llm_usage_includes_notice_strategy(temp_customer, temp_notice):
    with engine.begin() as conn:
        before = get_llm_usage_summary(conn, _ALL_TIME)
        conn.execute(
            insert(notice_strategy).values(
                customer_id=temp_customer, notice_id=temp_notice, status="done",
                input_tokens=1500, output_tokens=500, cost_usd=0.15,
            )
        )
        after = get_llm_usage_summary(conn, _ALL_TIME)

    assert after["breakdown"]["notice_strategy"]["calls"] == before["breakdown"]["notice_strategy"]["calls"] + 1
    assert after["breakdown"]["notice_strategy"]["tokens"] == before["breakdown"]["notice_strategy"]["tokens"] + 2000


def test_llm_usage_month_start_excludes_rows_before_cutoff(temp_notice):
    """"이번 달 누적" 필터(2026-09-12) — month_start 이전에 발생한 호출은 합산에서 빠져야 한다."""
    long_ago = datetime.now(timezone.utc) - timedelta(days=400)
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    with engine.begin() as conn:
        analysis_id = conn.execute(
            insert(analysis).values(
                notice_id=temp_notice, source_kind="notice", input_ref="test", step="A2_structure", status="done",
                llm_tokens=1000, llm_cost=0.05, created_at=long_ago,
            ).returning(analysis.c.id)
        ).scalar_one()
        excluded = get_llm_usage_summary(conn, cutoff)
        included = get_llm_usage_summary(conn, _ALL_TIME)

    try:
        assert excluded["breakdown"]["structure"]["tokens"] < included["breakdown"]["structure"]["tokens"]
    finally:
        with engine.begin() as conn:
            conn.execute(delete(analysis).where(analysis.c.id == analysis_id))
