"""입찰 자격요건(회사 단위) — 고객 자격 프로필 저장/조회 검증
(app/services/customer_eligibility.py, GET/PUT /api/customers/{id}/eligibility-profile)."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")
os.environ.setdefault("ADMIN_EMAIL", "report@grib.co.kr")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$argon2id$v=19$m=65536,t=3,p=4$9/7/Wg+VSkOsVCeiQiCz7w$bdDzJi9bKuERjBb6NHN0Ztk+X6uwxugL7kViHVRiqnY",
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import engine
from app.main import app
from app.models import audit_log, customer

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    response = c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    return c


@pytest.fixture
def customer_id(client: TestClient):
    response = client.post("/api/customers", json={"name": "[테스트] 자격요건 검증용 고객", "plan_tier": "standard"})
    assert response.status_code == 201
    cid = response.json()["id"]
    yield cid
    with engine.begin() as conn:
        conn.execute(customer.delete().where(customer.c.id == cid))


def test_get_eligibility_profile_defaults_to_unset(client: TestClient, customer_id: int):
    response = client.get(f"/api/customers/{customer_id}/eligibility-profile")
    assert response.status_code == 200
    body = response.json()
    assert body["company_size_tier"] is None
    assert body["has_research_institute"] is None
    assert body["venture_cert"] is None
    assert body["industry_codes"] == []
    assert body["certifications"] == []
    assert body["company_size_tiers"] == ["중소기업", "중견기업", "대기업"]


def test_get_eligibility_profile_404_for_unknown_customer(client: TestClient):
    response = client.get("/api/customers/999999999/eligibility-profile")
    assert response.status_code == 404


def test_put_eligibility_profile_saves_and_roundtrips(client: TestClient, customer_id: int):
    payload = {
        "company_size_tier": "중소기업",
        "has_research_institute": True,
        "venture_cert": False,
        "industry_codes": ["62010", "62021"],
        "certifications": ["ISO 9001"],
    }
    put_response = client.put(f"/api/customers/{customer_id}/eligibility-profile", json=payload)
    assert put_response.status_code == 204

    get_response = client.get(f"/api/customers/{customer_id}/eligibility-profile")
    body = get_response.json()
    assert body["company_size_tier"] == "중소기업"
    assert body["has_research_institute"] is True
    assert body["venture_cert"] is False
    assert body["industry_codes"] == ["62010", "62021"]
    assert body["certifications"] == ["ISO 9001"]


def test_put_eligibility_profile_rejects_invalid_company_size_tier(client: TestClient, customer_id: int):
    response = client.put(
        f"/api/customers/{customer_id}/eligibility-profile",
        json={"company_size_tier": "초대기업", "industry_codes": [], "certifications": []},
    )
    assert response.status_code == 400


def test_put_eligibility_profile_404_for_unknown_customer(client: TestClient):
    response = client.put(
        "/api/customers/999999999/eligibility-profile",
        json={"company_size_tier": None, "industry_codes": [], "certifications": []},
    )
    assert response.status_code == 404


def test_put_eligibility_profile_records_audit_log(client: TestClient, customer_id: int):
    response = client.put(
        f"/api/customers/{customer_id}/eligibility-profile",
        json={"company_size_tier": "중견기업", "industry_codes": [], "certifications": []},
    )
    assert response.status_code == 204
    with engine.connect() as conn:
        row = conn.execute(
            select(audit_log.c.action, audit_log.c.target_id)
            .where(audit_log.c.action == "customer.eligibility_profile", audit_log.c.target_id == str(customer_id))
            .order_by(audit_log.c.id.desc())
        ).first()
    assert row is not None
