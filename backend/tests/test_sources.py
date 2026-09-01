"""소스 관리 목록(관리자 페이지) 검증."""

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


def test_sources_requires_auth():
    response = TestClient(app).get("/api/admin/sources")
    assert response.status_code == 401


def test_sources_list_shape_and_sorted_by_org(client: TestClient):
    response = client.get("/api/admin/sources")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) > 0

    row = rows[0]
    assert {"id", "name", "org_name", "homepage_url", "adapter_type", "adapter_label", "stage", "status", "last_run_at"} <= row.keys()

    # 기관별로 묶여 있어야 한다 — DB 콜레이션이 파이썬 sorted()와 한글 정렬 기준이 다를 수 있어
    # 정확한 알파벳 순서 대신 "같은 기관명이 떨어져서 두 번 나타나지 않는지"만 확인한다
    named = [r["org_name"] for r in rows if r["org_name"] is not None]
    grouped_once = []
    for org_name in named:
        if not grouped_once or grouped_once[-1] != org_name:
            grouped_once.append(org_name)
    assert len(grouped_once) == len(set(named))


def test_sources_status_is_one_of_known_values(client: TestClient):
    rows = client.get("/api/admin/sources").json()
    for row in rows:
        assert row["status"] in {"ok", "warn", "fail", "inactive", "no_run_yet"}


# ---- 발주기관(agency) 중심 목록 — 2026-09-01 요청 ---------------------------------


def test_agencies_requires_auth():
    response = TestClient(app).get("/api/admin/sources/agencies")
    assert response.status_code == 401


def test_agencies_list_shape_and_hangul_first_sort(client: TestClient):
    response = client.get("/api/admin/sources/agencies")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) > 0

    row = rows[0]
    assert {"id", "name", "abbr", "category", "notice_url", "channel", "adapter_label", "status", "last_run_at"} <= row.keys()

    # 조달청·IRIS(공고기관/채널이지 발주기관이 아님)는 이 목록에 나오면 안 된다
    names = [r["name"] for r in rows]
    assert "조달청" not in names
    assert "IRIS" not in names

    # 한글 이름이 영어 이름보다 먼저 나와야 한다(2026-09-01 요청)
    is_hangul = [bool(r["name"]) and "가" <= r["name"][0] <= "힣" for r in rows]
    first_non_hangul = next((i for i, v in enumerate(is_hangul) if not v), len(is_hangul))
    assert all(is_hangul[:first_non_hangul])
    assert not any(is_hangul[first_non_hangul:])


def test_agencies_search_by_abbr(client: TestClient):
    rows = client.get("/api/admin/sources/agencies", params={"q": "NIPA"}).json()
    assert len(rows) == 1
    assert rows[0]["name"] == "정보통신산업진흥원"


def test_agencies_filter_by_status_no_source(client: TestClient):
    # KOCCA는 아직 소속 소스가 없는 시드 데이터(2026-09-01 seed) — "no_source" 상태여야 함
    rows = client.get("/api/admin/sources/agencies", params={"q": "KOCCA"}).json()
    assert len(rows) == 1
    assert rows[0]["status"] == "no_source"
    assert rows[0]["channel"] is None

    filtered = client.get("/api/admin/sources/agencies", params={"status": "no_source"}).json()
    assert any(r["abbr"] == "KOCCA" for r in filtered)
    assert all(r["status"] == "no_source" for r in filtered)
