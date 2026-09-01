"""관심주제 대분류(interest_topic) 관리자 CRUD 검증 — 2026-09-01 요청."""

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
from sqlalchemy import delete, select

from app.db import engine
from app.main import app
from app.models import audit_log, auth_session, interest_topic, login_attempt

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


@pytest.fixture
def _cleanup_test_topics():
    yield
    with engine.begin() as conn:
        ids = [
            row[0]
            for row in conn.execute(select(interest_topic.c.id).where(interest_topic.c.name.like("__test_%")))
        ]
        if ids:
            conn.execute(delete(audit_log).where(audit_log.c.target_type == "interest_topic", audit_log.c.target_id.in_([str(i) for i in ids])))
            conn.execute(delete(interest_topic).where(interest_topic.c.id.in_(ids)))


def test_topics_requires_auth():
    assert TestClient(app).get("/api/admin/topics").status_code == 401


def test_topics_list_includes_seeded_20(client: TestClient):
    rows = client.get("/api/admin/topics").json()
    assert len(rows) >= 20
    assert {"id", "name", "description", "sort_order", "active"} <= rows[0].keys()


def test_create_update_and_deactivate_topic(client: TestClient, _cleanup_test_topics):
    created = client.post("/api/admin/topics", json={"name": "__test_새분류", "sort_order": 999})
    assert created.status_code == 201
    topic_id = created.json()["id"]
    assert created.json()["active"] is True

    updated = client.patch(f"/api/admin/topics/{topic_id}", json={"description": "설명 추가"})
    assert updated.status_code == 200
    assert updated.json()["description"] == "설명 추가"

    deactivated = client.patch(f"/api/admin/topics/{topic_id}", json={"active": False})
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False

    # 감사 로그에 남아야 한다(CLAUDE.md 코드 규칙)
    with engine.connect() as conn:
        actions = conn.execute(
            select(audit_log.c.action).where(audit_log.c.target_type == "interest_topic", audit_log.c.target_id == str(topic_id))
        ).scalars().all()
    assert "topic.create" in actions
    assert actions.count("topic.update") == 2


def test_create_duplicate_name_rejected(client: TestClient, _cleanup_test_topics):
    first = client.post("/api/admin/topics", json={"name": "__test_중복분류"})
    assert first.status_code == 201
    dup = client.post("/api/admin/topics", json={"name": "__test_중복분류"})
    assert dup.status_code == 409


def test_update_missing_topic_is_404(client: TestClient):
    response = client.patch("/api/admin/topics/999999", json={"active": False})
    assert response.status_code == 404
