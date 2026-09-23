"""공고별 "AI 사업 추진 전략"(2026-09-05) — app/services/notice_strategy.py 검증.
실제 api.anthropic.com·나라장터·IRIS에 나가지 않는다."""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")
os.environ.setdefault("ADMIN_EMAIL", "report@grib.co.kr")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$argon2id$v=19$m=65536,t=3,p=4$9/7/Wg+VSkOsVCeiQiCz7w$bdDzJi9bKuERjBb6NHN0Ztk+X6uwxugL7kViHVRiqnY",
)

import pytest
from sqlalchemy import delete, insert, select

from app.config import settings
from app.db import engine
from app.models import analysis, customer, notice, notice_strategy, source
from app.services.notice_strategy import (
    LLMNotConfiguredError,
    get_or_generate_strategy,
    get_public_notice_summary,
)

_SUMMARY_MD = "## 공고 핵심 요약\n- 테스트용 전략 문서\n"


def _any_source_id(conn) -> int:
    return conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()


@pytest.fixture
def temp_notice():
    with engine.begin() as conn:
        notice_id = conn.execute(
            insert(notice).values(
                source_id=_any_source_id(conn), source_ver=1, stage="입찰공고",
                title="[테스트] 전략 생성 검증용 공고", url="https://example.grib-test.kr/notice/strategy-test",
            ).returning(notice.c.id)
        ).scalar_one()
    yield notice_id
    with engine.begin() as conn:
        conn.execute(delete(notice_strategy).where(notice_strategy.c.notice_id == notice_id))
        conn.execute(delete(analysis).where(analysis.c.notice_id == notice_id))
        conn.execute(delete(notice).where(notice.c.id == notice_id))


@pytest.fixture
def temp_customer():
    with engine.begin() as conn:
        customer_id = conn.execute(
            insert(customer).values(name="[테스트] 전략 생성 검증용 고객", plan_tier="standard").returning(customer.c.id)
        ).scalar_one()
    yield customer_id
    with engine.begin() as conn:
        conn.execute(delete(notice_strategy).where(notice_strategy.c.customer_id == customer_id))
        conn.execute(delete(customer).where(customer.c.id == customer_id))


def _mock_anthropic_response(text: str, input_tokens: int = 400, output_tokens: int = 300) -> mock.Mock:
    resp = mock.Mock()
    resp.json.return_value = {
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }
    return resp


def test_get_public_notice_summary_excludes_internal_fields(temp_notice: int):
    with engine.connect() as conn:
        result = get_public_notice_summary(conn, temp_notice)
    assert result is not None
    assert "we_qualify" not in result
    assert "assignee_name" not in result
    assert "org_followed" not in result
    assert {"notice_type", "notice_status_label", "work_type_label"} <= result.keys()
    assert result["ai_summary"] is None


def test_get_public_notice_summary_includes_ai_summary_when_done(temp_notice: int):
    with engine.begin() as conn:
        conn.execute(
            insert(analysis).values(
                notice_id=temp_notice, source_kind="notice", input_ref="x", status="done", step="A2_structure", ver=1,
                summary={"purpose": "테스트 목적"},
            )
        )
    with engine.connect() as conn:
        result = get_public_notice_summary(conn, temp_notice)
    assert result["ai_summary"] == {"purpose": "테스트 목적"}


def test_get_public_notice_summary_404_for_unknown_notice():
    with engine.connect() as conn:
        assert get_public_notice_summary(conn, 999999999) is None


def test_get_or_generate_strategy_rejects_unknown_model(temp_customer: int, temp_notice: int):
    with pytest.raises(ValueError, match="허용되지 않은 모델"):
        get_or_generate_strategy(temp_customer, temp_notice, model="gpt-4")
    with engine.connect() as conn:
        exists = conn.execute(
            select(notice_strategy.c.id).where(notice_strategy.c.customer_id == temp_customer, notice_strategy.c.notice_id == temp_notice)
        ).first()
    assert exists is None  # 검증 실패는 선점(row 생성) 전에 걸려야 함


def test_get_or_generate_strategy_requires_api_key(temp_customer: int, temp_notice: int, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(LLMNotConfiguredError):
        get_or_generate_strategy(temp_customer, temp_notice)
    with engine.connect() as conn:
        row = conn.execute(
            select(notice_strategy.c.status).where(notice_strategy.c.customer_id == temp_customer, notice_strategy.c.notice_id == temp_notice)
        ).mappings().one()
    assert row["status"] == "failed"


def test_get_or_generate_strategy_happy_path_then_idempotent(temp_customer: int, temp_notice: int, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with mock.patch("app.services.notice_strategy.fetch", return_value=_mock_anthropic_response(_SUMMARY_MD)) as mock_fetch:
        first = get_or_generate_strategy(temp_customer, temp_notice)
        assert first["status"] == "done"
        assert first["strategy_md"] == _SUMMARY_MD
        assert mock_fetch.call_count == 1

        # 여러 번 호출해도(=고객이 여러 번 눌러도) 실제 LLM 호출은 늘어나지 않는다.
        second = get_or_generate_strategy(temp_customer, temp_notice)
        assert second == first
        assert mock_fetch.call_count == 1

        third = get_or_generate_strategy(temp_customer, temp_notice)
        assert mock_fetch.call_count == 1
        assert third["strategy_md"] == _SUMMARY_MD


def test_get_or_generate_strategy_returns_pending_without_calling_llm(temp_customer: int, temp_notice: int, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.begin() as conn:
        conn.execute(insert(notice_strategy).values(customer_id=temp_customer, notice_id=temp_notice, status="pending"))

    with mock.patch("app.services.notice_strategy.fetch") as mock_fetch:
        result = get_or_generate_strategy(temp_customer, temp_notice)
    assert result == {"status": "pending"}
    mock_fetch.assert_not_called()


def test_get_or_generate_strategy_retries_after_failure(temp_customer: int, temp_notice: int, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.begin() as conn:
        conn.execute(
            insert(notice_strategy).values(customer_id=temp_customer, notice_id=temp_notice, status="failed", error_message="이전 실패")
        )

    with mock.patch("app.services.notice_strategy.fetch", return_value=_mock_anthropic_response(_SUMMARY_MD)) as mock_fetch:
        result = get_or_generate_strategy(temp_customer, temp_notice)
    assert result["status"] == "done"
    mock_fetch.assert_called_once()
