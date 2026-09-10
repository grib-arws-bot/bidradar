"""리포트 AI 코멘트(2026-09-05) — app/services/report_commentary.py 검증. 공고 선별은
이미 규칙 기반(interest_report.generate_report)으로 끝난 상태를 그대로 두고, "왜 의미있는지"
코멘트만 LLM이 덧붙이는지 확인한다. 실제 api.anthropic.com에 나가지 않는다."""

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
from app.models import customer, newsletter_report
from app.services.report_commentary import (
    LLMNotConfiguredError,
    NoProfileError,
    ReportNotFoundError,
    generate_report_commentary,
)

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"

_NOTICES = [
    {"id": 1, "title": "산업안전 CCTV 구축", "stage": "입찰공고", "org_name": "한국산업안전공단",
     "est_price": 100000000, "close_dt": None, "score": 8},
    {"id": 2, "title": "스마트교육 플랫폼 구축", "stage": "입찰공고", "org_name": "교육청",
     "est_price": 50000000, "close_dt": None, "score": 6},
]


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    return c


@pytest.fixture
def temp_customer():
    with engine.begin() as conn:
        customer_id = conn.execute(
            insert(customer).values(name="[테스트] 리포트 코멘트 검증용", plan_tier="standard")
            .returning(customer.c.id)
        ).scalar_one()
    yield customer_id
    with engine.begin() as conn:
        conn.execute(newsletter_report.delete().where(newsletter_report.c.customer_id == customer_id))
        conn.execute(customer.delete().where(customer.c.id == customer_id))


@pytest.fixture
def temp_report(temp_customer):
    with engine.begin() as conn:
        report_id = conn.execute(
            insert(newsletter_report).values(
                customer_id=temp_customer, token=f"test-token-{temp_customer}", notices=_NOTICES, summary={},
            ).returning(newsletter_report.c.id)
        ).scalar_one()
    return report_id


def _mock_anthropic_response(items: list[dict], input_tokens: int = 800, output_tokens: int = 400) -> mock.Mock:
    resp = mock.Mock()
    resp.json.return_value = {
        "content": [{"type": "tool_use", "name": "annotate_notices", "input": {"items": items}}],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }
    return resp


def _set_profile(customer_id: int, md: str = "## 회사 개요\n산업안전 솔루션 기업") -> None:
    with engine.begin() as conn:
        conn.execute(
            customer.update().where(customer.c.id == customer_id).values(profile_summary_md=md)
        )


def test_generate_commentary_requires_api_key(temp_report, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with engine.begin() as conn:
        with pytest.raises(LLMNotConfiguredError):
            generate_report_commentary(conn, temp_report)


def test_generate_commentary_rejects_unknown_model(temp_report, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.begin() as conn:
        with pytest.raises(ValueError, match="허용되지 않은 모델"):
            generate_report_commentary(conn, temp_report, model="gpt-4")


def test_generate_commentary_404_unknown_report(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.begin() as conn:
        with pytest.raises(ReportNotFoundError):
            generate_report_commentary(conn, 999999999)


def test_generate_commentary_requires_profile_summary_first(temp_report, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.begin() as conn:
        with pytest.raises(NoProfileError):
            generate_report_commentary(conn, temp_report)


def test_generate_commentary_merges_into_notices_and_records_cost(temp_report, temp_customer, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    _set_profile(temp_customer)
    items = [
        {"notice_id": 1, "commentary": "CCTV 영상분석 역량과 직접 관련", "strategy": "레퍼런스 강조"},
        {"notice_id": 2, "commentary": "스마트교육 분야와 관련성 낮음", "strategy": "선택적 참여 검토"},
    ]
    with mock.patch(
        "app.services.report_commentary.fetch", return_value=_mock_anthropic_response(items)
    ) as mock_fetch:
        with engine.begin() as conn:
            result = generate_report_commentary(conn, temp_report)

    assert mock_fetch.call_args.kwargs["headers"]["x-api-key"] == "sk-ant-test"
    assert result == {
        "annotated": 2, "input_tokens": 800, "output_tokens": 400,
        "cost_usd": round(800 / 1e6 * 3.00 + 400 / 1e6 * 15.00, 4),
    }

    with engine.connect() as conn:
        row = conn.execute(
            select(newsletter_report.c.notices, newsletter_report.c.ai_generated_at, newsletter_report.c.ai_tokens)
            .where(newsletter_report.c.id == temp_report)
        ).first()
    assert row.ai_generated_at is not None
    assert row.ai_tokens == 1200
    by_id = {n["id"]: n for n in row.notices}
    assert by_id[1]["ai_commentary"] == "CCTV 영상분석 역량과 직접 관련"
    assert by_id[1]["ai_strategy"] == "레퍼런스 강조"
    assert by_id[2]["ai_commentary"] == "스마트교육 분야와 관련성 낮음"
    # 원 필드(제목·기관 등)는 그대로 보존돼야 한다 — 규칙 기반 선별 결과를 덮어쓰지 않음.
    assert by_id[1]["title"] == "산업안전 CCTV 구축"


def test_generate_commentary_empty_notices_short_circuits(temp_customer, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    _set_profile(temp_customer)
    with engine.begin() as conn:
        report_id = conn.execute(
            insert(newsletter_report).values(
                customer_id=temp_customer, token=f"empty-token-{temp_customer}", notices=[], summary={},
            ).returning(newsletter_report.c.id)
        ).scalar_one()

    with mock.patch("app.services.report_commentary.fetch") as mock_fetch:
        with engine.begin() as conn:
            result = generate_report_commentary(conn, report_id)
    mock_fetch.assert_not_called()
    assert result == {"annotated": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}


# ---- API 라우트 --------------------------------------------------------------------


def test_ai_commentary_route_requires_auth():
    response = TestClient(app).post("/api/customers/1/reports/1/ai-commentary", json={"model": "sonnet"})
    assert response.status_code == 401


def test_ai_commentary_route_404_unknown_report(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    response = client.post("/api/customers/1/reports/999999999/ai-commentary", json={"model": "sonnet"})
    assert response.status_code == 404


def test_ai_commentary_route_422_without_profile(client: TestClient, temp_report: int, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    response = client.post(f"/api/customers/1/reports/{temp_report}/ai-commentary", json={"model": "sonnet"})
    assert response.status_code == 422


def test_ai_commentary_route_happy_path(client: TestClient, temp_report: int, temp_customer: int, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    _set_profile(temp_customer)
    items = [{"notice_id": 1, "commentary": "관련성 높음", "strategy": "제안서 강조"},
              {"notice_id": 2, "commentary": "관련성 낮음", "strategy": "검토 후 결정"}]
    with mock.patch("app.services.report_commentary.fetch", return_value=_mock_anthropic_response(items)):
        response = client.post(f"/api/customers/{temp_customer}/reports/{temp_report}/ai-commentary", json={"model": "sonnet"})
    assert response.status_code == 200
    assert response.json()["annotated"] == 2


def test_ai_commentary_route_501_without_api_key(client: TestClient, temp_report: int, temp_customer: int, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    _set_profile(temp_customer)
    response = client.post(f"/api/customers/{temp_customer}/reports/{temp_report}/ai-commentary", json={"model": "sonnet"})
    assert response.status_code == 501
