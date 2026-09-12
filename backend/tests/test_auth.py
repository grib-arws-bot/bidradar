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

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import engine
from app.main import app
from app.models import auth_session

CORRECT_PASSWORD = "dev-local-test-pw-123"
EMAIL = "report@grib.co.kr"


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


def test_login_default_session_is_12h(client: TestClient):
    response = client.post("/api/auth/login", json={"email": EMAIL, "password": CORRECT_PASSWORD})
    assert response.status_code == 200
    assert response.cookies["bidradar_session"]
    # httpx TestClient는 쿠키의 max-age를 노출 안 하므로 DB에 저장된 만료시각으로 검증한다.
    # 2026-09-13 트랜잭션 격리 도입 후 auth_session에 기존 실세션도 같이 보이므로(같은
    # 커넥션이라 당연히 보임 — conftest.py 참고), 방금 이 로그인이 만든 것(최신 id)만 본다.
    with engine.begin() as conn:
        expires_at = conn.execute(
            select(auth_session.c.expires_at).order_by(auth_session.c.id.desc()).limit(1)
        ).scalar_one()
    remaining = expires_at - datetime.now(timezone.utc)
    assert timedelta(hours=11) < remaining <= timedelta(hours=12)


def test_login_remember_extends_session_to_30d(client: TestClient):
    response = client.post(
        "/api/auth/login", json={"email": EMAIL, "password": CORRECT_PASSWORD, "remember": True}
    )
    assert response.status_code == 200
    with engine.begin() as conn:
        expires_at = conn.execute(
            select(auth_session.c.expires_at).order_by(auth_session.c.id.desc()).limit(1)
        ).scalar_one()
    remaining = expires_at - datetime.now(timezone.utc)
    assert timedelta(days=29) < remaining <= timedelta(days=30)


def test_lockout_after_five_failures(client: TestClient):
    for _ in range(5):
        response = client.post("/api/auth/login", json={"email": EMAIL, "password": "wrong-password"})
        assert response.status_code == 401

    # 6번째는 자격증명이 맞아도 잠겨서 429
    locked = client.post("/api/auth/login", json={"email": EMAIL, "password": CORRECT_PASSWORD})
    assert locked.status_code == 429


def test_dev_autologin_succeeds_when_enabled(client: TestClient):
    original = settings.enable_dev_autologin
    settings.enable_dev_autologin = True
    try:
        response = client.post("/api/auth/dev-autologin")
        assert response.status_code == 200
        assert response.json()["email"] == EMAIL
        assert "bidradar_session" in response.cookies

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == EMAIL
    finally:
        settings.enable_dev_autologin = original


def test_dev_autologin_404_by_default(client: TestClient):
    # stg(docker-compose 로컬 기동)도 prod와 동일하게 로그인 절차를 거쳐야 하므로 기본값은
    # 항상 꺼져 있어야 한다(2026-09-03) — environment(is_dev)와 무관.
    assert settings.enable_dev_autologin is False
    response = client.post("/api/auth/dev-autologin")
    assert response.status_code == 404
    assert "bidradar_session" not in response.cookies
