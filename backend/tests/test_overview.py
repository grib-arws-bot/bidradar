"""관리자 홈 대시보드(전체 시스템 현황) 검증."""

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
from sqlalchemy import delete

from app.db import engine
from app.main import app
from app.models import auth_session, login_attempt

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"


@pytest.fixture(autouse=True)
def _clean_auth_tables():
    with engine.begin() as conn:
        conn.execute(delete(auth_session))
        conn.execute(delete(login_attempt))
    yield


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    return c


def test_overview_requires_auth():
    response = TestClient(app).get("/api/overview")
    assert response.status_code == 401


def test_overview_shape(client: TestClient):
    response = client.get("/api/overview")
    assert response.status_code == 200
    body = response.json()
    assert {"sources", "notices", "customers", "recent_reports"} <= body.keys()
    assert body["notices"]["total"] > 0
    assert body["customers"]["total"] > 0
    assert sum(body["sources"]["counts"].values()) == len(body["sources"]["sources"])
