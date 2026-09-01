"""U3 완료조건 검증: 단일 계정 로그인 · 5회 실패 잠금(계정+IP, 03절 v0.3)."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")
os.environ.setdefault("ADMIN_EMAIL", "report@grib.co.kr")
# hash_password("dev-local-test-pw-123")
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

CORRECT_PASSWORD = "dev-local-test-pw-123"
EMAIL = "report@grib.co.kr"


@pytest.fixture(autouse=True)
def _clean_auth_tables():
    with engine.begin() as conn:
        conn.execute(delete(auth_session))
        conn.execute(delete(login_attempt))
    yield
    with engine.begin() as conn:
        conn.execute(delete(auth_session))
        conn.execute(delete(login_attempt))


@pytest.fixture
def client():
    return TestClient(app)


def test_login_success_sets_cookie_and_me_works(client: TestClient):
    response = client.post("/api/auth/login", json={"email": EMAIL, "password": CORRECT_PASSWORD})
    assert response.status_code == 200
    assert "bidradar_session" in response.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL


def test_login_wrong_password_rejected(client: TestClient):
    response = client.post("/api/auth/login", json={"email": EMAIL, "password": "wrong-password"})
    assert response.status_code == 401
    assert "bidradar_session" not in response.cookies


def test_me_without_cookie_is_401(client: TestClient):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_lockout_after_five_failures(client: TestClient):
    for _ in range(5):
        response = client.post("/api/auth/login", json={"email": EMAIL, "password": "wrong-password"})
        assert response.status_code == 401

    # 6번째는 자격증명이 맞아도 잠겨서 429
    locked = client.post("/api/auth/login", json={"email": EMAIL, "password": CORRECT_PASSWORD})
    assert locked.status_code == 429
