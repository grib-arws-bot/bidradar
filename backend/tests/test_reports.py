"""관심주제 리포트 + 서명된 공유 링크(로그인 없음) 검증."""

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
    response = c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    return c


@pytest.fixture
def grib_customer_id(client: TestClient) -> int:
    customers = client.get("/api/customers").json()
    return next(c["id"] for c in customers if c["plan_tier"] == "internal")


def test_generate_report_creates_snapshot(client: TestClient, grib_customer_id: int):
    response = client.post(f"/api/customers/{grib_customer_id}/reports")
    assert response.status_code == 201
    body = response.json()
    assert body["token"]
    assert body["customer_id"] == grib_customer_id
    assert "notices" in body and "summary" in body
    assert body["summary"]["total"] == len(body["notices"])


def test_generate_report_summary_includes_attributions_list(client: TestClient, grib_customer_id: int):
    # advisory INBOX #7(2026-09-01) — 출처표시 문구는 사람이 붙이는 게 아니라 생성 시점에
    # source.attribution_text에서 자동으로 모여야 한다(내용 자체는 시드 소스 배정에 따라
    # 달라질 수 있어 타입/키 존재만 검증).
    response = client.post(f"/api/customers/{grib_customer_id}/reports")
    body = response.json()
    assert isinstance(body["summary"]["attributions"], list)
    assert all(isinstance(a, str) for a in body["summary"]["attributions"])


def test_generate_report_404_for_unknown_customer(client: TestClient):
    response = client.post("/api/customers/999999/reports")
    assert response.status_code == 404


def test_list_reports_returns_generated(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    listed = client.get(f"/api/customers/{grib_customer_id}/reports").json()
    assert any(r["token"] == created["token"] for r in listed)


def test_public_report_requires_no_auth(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()

    anon = TestClient(app)  # 로그인 안 함
    response = anon.get(f"/api/public/reports/{created['token']}")
    assert response.status_code == 200
    body = response.json()
    assert body["customer_name"]
    assert body["notices"] == created["notices"]


def test_public_report_unknown_token_404():
    anon = TestClient(app)
    response = anon.get("/api/public/reports/does-not-exist")
    assert response.status_code == 404


def test_public_report_view_count_increments(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    token = created["token"]
    anon = TestClient(app)

    first = anon.get(f"/api/public/reports/{token}").json()
    second = anon.get(f"/api/public/reports/{token}").json()
    assert second["view_count"] == first["view_count"] + 1


def test_report_snapshot_is_frozen_after_profile_change(client: TestClient, grib_customer_id: int):
    topics = client.get(f"/api/customers/{grib_customer_id}/interests").json()["topics"]
    client.put(
        f"/api/customers/{grib_customer_id}/interests",
        json={"topic_ids": [topics[0]["id"]], "terms": [], "followed_org_ids": [], "regions": []},
    )
    created = client.post(f"/api/customers/{grib_customer_id}/reports")
    snapshot = created.json()["notices"]

    # 프로필을 완전히 바꿔도(빈 프로필로) 이미 생성된 리포트 스냅샷은 그대로여야 함.
    client.put(
        f"/api/customers/{grib_customer_id}/interests",
        json={"topic_ids": [], "terms": [], "followed_org_ids": [], "regions": []},
    )
    anon = TestClient(app)
    fetched = anon.get(f"/api/public/reports/{created.json()['token']}").json()
    assert fetched["notices"] == snapshot
