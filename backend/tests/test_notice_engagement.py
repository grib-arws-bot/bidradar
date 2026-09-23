"""행동 데이터(좋아요/클릭/상세보기, 2026-09-23) — app/services/notice_engagement.py 검증."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")
os.environ.setdefault("ADMIN_EMAIL", "report@grib.co.kr")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$argon2id$v=19$m=65536,t=3,p=4$9/7/Wg+VSkOsVCeiQiCz7w$bdDzJi9bKuERjBb6NHN0Ztk+X6uwxugL7kViHVRiqnY",
)

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import customer, notice, notice_engagement_event, source
from app.services.notice_engagement import get_like_state, record_click, record_view, set_like


def _any_source_id(conn) -> int:
    return conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()


@pytest.fixture
def temp_notice():
    with engine.begin() as conn:
        notice_id = conn.execute(
            insert(notice).values(
                source_id=_any_source_id(conn), source_ver=1, stage="입찰공고",
                title="[테스트] 행동 데이터 검증용 공고", url="https://example.grib-test.kr/notice/engagement-test",
            ).returning(notice.c.id)
        ).scalar_one()
    yield notice_id
    with engine.begin() as conn:
        conn.execute(delete(notice_engagement_event).where(notice_engagement_event.c.notice_id == notice_id))
        conn.execute(delete(notice).where(notice.c.id == notice_id))


@pytest.fixture
def temp_customer():
    with engine.begin() as conn:
        customer_id = conn.execute(
            insert(customer).values(name="[테스트] 행동 데이터 검증용 고객", plan_tier="standard").returning(customer.c.id)
        ).scalar_one()
    yield customer_id
    with engine.begin() as conn:
        conn.execute(delete(notice_engagement_event).where(notice_engagement_event.c.customer_id == customer_id))
        conn.execute(delete(customer).where(customer.c.id == customer_id))


def _event_count(customer_id: int, notice_id: int, event_type: str) -> int:
    with engine.connect() as conn:
        return len(conn.execute(
            select(notice_engagement_event.c.id).where(
                notice_engagement_event.c.customer_id == customer_id,
                notice_engagement_event.c.notice_id == notice_id,
                notice_engagement_event.c.event_type == event_type,
            )
        ).all())


def test_record_click_dedupes_within_window(temp_customer: int, temp_notice: int):
    record_click(temp_customer, temp_notice)
    record_click(temp_customer, temp_notice)  # 5초 윈도우 안 — 새 행 안 쌓임
    assert _event_count(temp_customer, temp_notice, "click") == 1


def test_record_click_creates_new_row_after_window_passes(temp_customer: int, temp_notice: int):
    """created_at은 DB server_default(now())라 앱 레이어에서 시간을 모킹해도 실제 저장되는
    값에는 영향이 없다 — 대신 이미 지난 시각으로 이벤트 행을 직접 심어 "윈도우가 지났다"는
    상황을 재현한다."""
    old_time = datetime.now(timezone.utc) - timedelta(seconds=10)
    with engine.begin() as conn:
        conn.execute(
            insert(notice_engagement_event).values(
                customer_id=temp_customer, notice_id=temp_notice, event_type="click", created_at=old_time,
            )
        )
    record_click(temp_customer, temp_notice)  # de-dupe 윈도우(5초)를 지났으므로 새 행 쌓임
    assert _event_count(temp_customer, temp_notice, "click") == 2


def test_record_view_dedupes_within_window(temp_customer: int, temp_notice: int):
    record_view(temp_customer, temp_notice)
    record_view(temp_customer, temp_notice)  # 5분 윈도우 안
    assert _event_count(temp_customer, temp_notice, "view") == 1


def test_record_click_and_view_are_independent(temp_customer: int, temp_notice: int):
    record_click(temp_customer, temp_notice)
    record_view(temp_customer, temp_notice)
    assert _event_count(temp_customer, temp_notice, "click") == 1
    assert _event_count(temp_customer, temp_notice, "view") == 1


def test_get_like_state_false_when_no_events(temp_customer: int, temp_notice: int):
    with engine.connect() as conn:
        assert get_like_state(conn, temp_customer, temp_notice) is False


def test_set_like_true_then_get_like_state_reflects_it(temp_customer: int, temp_notice: int):
    result = set_like(temp_customer, temp_notice, None, True)
    assert result is True
    with engine.connect() as conn:
        assert get_like_state(conn, temp_customer, temp_notice) is True


def test_set_like_is_idempotent_when_already_in_desired_state(temp_customer: int, temp_notice: int):
    set_like(temp_customer, temp_notice, None, True)
    set_like(temp_customer, temp_notice, None, True)  # 이미 liked=True — 새 이벤트 안 쌓임
    assert _event_count(temp_customer, temp_notice, "like") == 1


def test_set_like_toggle_sequence_reflects_latest_state(temp_customer: int, temp_notice: int):
    set_like(temp_customer, temp_notice, None, True)
    set_like(temp_customer, temp_notice, None, False)
    set_like(temp_customer, temp_notice, None, True)
    with engine.connect() as conn:
        assert get_like_state(conn, temp_customer, temp_notice) is True
    # like -> unlike -> like: 세 이벤트 모두 실제로 쌓였는지(멱등 체크가 잘못 걸러내지 않았는지)
    assert _event_count(temp_customer, temp_notice, "like") == 2
    assert _event_count(temp_customer, temp_notice, "unlike") == 1


def test_set_like_unlike_after_like_reflects_false(temp_customer: int, temp_notice: int):
    set_like(temp_customer, temp_notice, None, True)
    result = set_like(temp_customer, temp_notice, None, False)
    assert result is False
    with engine.connect() as conn:
        assert get_like_state(conn, temp_customer, temp_notice) is False
