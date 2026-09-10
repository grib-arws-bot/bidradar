"""고객 프로필 요약(2026-09-05, "Phase 1" 보고서 최적화, "B로 하자" 결정) —
app/services/customer_profile.py 검증. 실제 api.anthropic.com에 나가지 않는다."""

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
from fastapi.testclient import TestClient
from sqlalchemy import insert, select

from app.config import settings
from app.db import engine
from app.main import app
from app.models import customer, customer_document
from app.services.customer_profile import (
    LLMNotConfiguredError,
    NoDocumentsError,
    save_manual_profile_summary,
    summarize_customer_profile,
)

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"

_SUMMARY_MD = "## 회사 개요\n그립은 산업안전관리 솔루션 기업이다.\n"


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    return c


@pytest.fixture
def temp_customer():
    with engine.begin() as conn:
        customer_id = conn.execute(
            insert(customer).values(name="[테스트] 프로필 요약 검증용", plan_tier="standard")
            .returning(customer.c.id)
        ).scalar_one()
    yield customer_id
    with engine.begin() as conn:
        conn.execute(customer_document.delete().where(customer_document.c.customer_id == customer_id))
        conn.execute(customer.delete().where(customer.c.id == customer_id))


def _mock_anthropic_response(text: str, input_tokens: int = 500, output_tokens: int = 300) -> mock.Mock:
    resp = mock.Mock()
    resp.json.return_value = {
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }
    return resp


def test_summarize_requires_api_key(temp_customer, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with engine.begin() as conn:
        with pytest.raises(LLMNotConfiguredError):
            summarize_customer_profile(conn, temp_customer)


def test_summarize_rejects_unknown_model(temp_customer, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.begin() as conn:
        with pytest.raises(ValueError, match="허용되지 않은 모델"):
            summarize_customer_profile(conn, temp_customer, model="gpt-4")


def test_summarize_requires_at_least_one_document(temp_customer, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.begin() as conn:
        with pytest.raises(NoDocumentsError):
            summarize_customer_profile(conn, temp_customer)


def test_summarize_saves_markdown_and_cost(temp_customer, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.begin() as conn:
        conn.execute(
            insert(customer_document).values(
                customer_id=temp_customer, filename="회사소개서.hwpx", content_type="application/haansofthwp+zip",
                content=b"fake", size_bytes=4,
            )
        )

    with mock.patch(
        "app.services.customer_profile.extract_document",
        return_value=mock.Mock(ok=True, text="그립은 산업안전관리 솔루션 기업입니다.", error=None),
    ), mock.patch(
        "app.services.customer_profile.fetch", return_value=_mock_anthropic_response(_SUMMARY_MD)
    ) as mock_fetch:
        with engine.begin() as conn:
            result = summarize_customer_profile(conn, temp_customer)

    assert mock_fetch.call_args.kwargs["headers"]["x-api-key"] == "sk-ant-test"
    assert result == {
        "summary_md": _SUMMARY_MD, "input_tokens": 500, "output_tokens": 300,
        "cost_usd": round(500 / 1e6 * 3.00 + 300 / 1e6 * 15.00, 4),
    }

    with engine.connect() as conn:
        row = conn.execute(
            select(customer.c.profile_summary_md, customer.c.profile_summarized_at, customer.c.profile_summary_tokens)
            .where(customer.c.id == temp_customer)
        ).first()
    assert row.profile_summary_md == _SUMMARY_MD
    assert row.profile_summarized_at is not None
    assert row.profile_summary_tokens == 800


def test_summarize_accumulates_tokens_across_reruns(temp_customer, monkeypatch):
    """재요약은 관리자가 버튼을 다시 눌러야만 일어난다 — 누적 비용은 그대로 더해져야 한다."""
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.begin() as conn:
        conn.execute(
            insert(customer_document).values(
                customer_id=temp_customer, filename="회사소개서.hwpx", content_type="application/haansofthwp+zip",
                content=b"fake", size_bytes=4,
            )
        )

    with mock.patch(
        "app.services.customer_profile.extract_document",
        return_value=mock.Mock(ok=True, text="소개 문단", error=None),
    ), mock.patch("app.services.customer_profile.fetch", return_value=_mock_anthropic_response(_SUMMARY_MD)):
        with engine.begin() as conn:
            summarize_customer_profile(conn, temp_customer)
        with engine.begin() as conn:
            summarize_customer_profile(conn, temp_customer)

    with engine.connect() as conn:
        tokens = conn.execute(
            select(customer.c.profile_summary_tokens).where(customer.c.id == temp_customer)
        ).scalar_one()
    assert tokens == 1600  # 800 * 2


# ---- API 라우트 --------------------------------------------------------------------


def test_profile_summarize_route_requires_auth():
    response = TestClient(app).post("/api/customers/1/profile/summarize", json={"model": "sonnet"})
    assert response.status_code == 401


def test_profile_summarize_route_404_unknown_customer(client: TestClient):
    response = client.post("/api/customers/999999999/profile/summarize", json={"model": "sonnet"})
    assert response.status_code == 404


def test_profile_summarize_route_422_without_documents(client: TestClient, temp_customer: int, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    response = client.post(f"/api/customers/{temp_customer}/profile/summarize", json={"model": "sonnet"})
    assert response.status_code == 422


def test_profile_summarize_route_happy_path(client: TestClient, temp_customer: int, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.begin() as conn:
        conn.execute(
            insert(customer_document).values(
                customer_id=temp_customer, filename="회사소개서.hwpx", content_type="application/haansofthwp+zip",
                content=b"fake", size_bytes=4,
            )
        )
    with mock.patch(
        "app.services.customer_profile.extract_document",
        return_value=mock.Mock(ok=True, text="소개 문단", error=None),
    ), mock.patch("app.services.customer_profile.fetch", return_value=_mock_anthropic_response(_SUMMARY_MD)):
        response = client.post(f"/api/customers/{temp_customer}/profile/summarize", json={"model": "sonnet"})
    assert response.status_code == 200
    assert response.json()["summary_md"] == _SUMMARY_MD


def test_profile_summarize_route_501_without_api_key(client: TestClient, temp_customer: int, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    response = client.post(f"/api/customers/{temp_customer}/profile/summarize", json={"model": "sonnet"})
    assert response.status_code == 501


# ---- 수동 편집("개조식으로 다듬기") -------------------------------------------------


def test_save_manual_profile_summary_updates_text_without_touching_generated_at(temp_customer):
    edited_md = "## 회사 개요\n- 산업안전 솔루션 기업\n- 직접 손질한 내용\n"
    with engine.begin() as conn:
        save_manual_profile_summary(conn, temp_customer, edited_md)

    with engine.connect() as conn:
        row = conn.execute(
            select(customer.c.profile_summary_md, customer.c.profile_summarized_at).where(
                customer.c.id == temp_customer
            )
        ).first()
    assert row.profile_summary_md == edited_md
    assert row.profile_summarized_at is None  # 수동 편집은 "AI 생성 시각"을 갱신하지 않는다


def test_profile_summary_edit_route_requires_auth():
    response = TestClient(app).patch("/api/customers/1/profile", json={"summary_md": "x"})
    assert response.status_code == 401


def test_profile_summary_edit_route_404_unknown_customer(client: TestClient):
    response = client.patch("/api/customers/999999999/profile", json={"summary_md": "x"})
    assert response.status_code == 404


def test_profile_summary_edit_route_happy_path(client: TestClient, temp_customer: int):
    edited_md = "## 회사 개요\n- 개조식으로 다듬은 내용\n"
    response = client.patch(f"/api/customers/{temp_customer}/profile", json={"summary_md": edited_md})
    assert response.status_code == 200
    assert response.json()["summary_md"] == edited_md

    rows = client.get("/api/customers/full").json()
    row = next(r for r in rows if r["id"] == temp_customer)
    assert row["profile_summary_md"] == edited_md
