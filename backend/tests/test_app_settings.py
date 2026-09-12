"""범용 앱 설정(2026-09-12) — app/services/app_settings.py + app/api/settings.py 검증."""

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

from app.db import engine
from app.main import app
from app.services.app_settings import get_report_retention_days, set_report_retention_days

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    return c


@pytest.fixture(autouse=True)
def _reset_report_retention():
    """다른 테스트가 남긴 값에 영향받지 않도록 매 테스트 전후로 초기화한다."""
    with engine.begin() as conn:
        set_report_retention_days(conn, None)
    yield
    with engine.begin() as conn:
        set_report_retention_days(conn, None)


def test_get_settings_requires_auth():
    response = TestClient(app).get("/api/settings")
    assert response.status_code == 401


def test_get_settings_defaults_to_none(client: TestClient):
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json()["report_retention_days"] is None


def test_put_settings_updates_report_retention_days(client: TestClient):
    response = client.put("/api/settings", json={"report_retention_days": 90})
    assert response.status_code == 200
    assert response.json()["report_retention_days"] == 90

    assert client.get("/api/settings").json()["report_retention_days"] == 90


def test_put_settings_can_disable_by_setting_null(client: TestClient):
    client.put("/api/settings", json={"report_retention_days": 30})
    response = client.put("/api/settings", json={"report_retention_days": None})
    assert response.status_code == 200
    assert response.json()["report_retention_days"] is None


def test_put_settings_rejects_less_than_one_day(client: TestClient):
    response = client.put("/api/settings", json={"report_retention_days": 0})
    assert response.status_code == 400


def test_set_get_report_retention_days_round_trip():
    with engine.begin() as conn:
        set_report_retention_days(conn, 45)
    with engine.connect() as conn:
        assert get_report_retention_days(conn) == 45
