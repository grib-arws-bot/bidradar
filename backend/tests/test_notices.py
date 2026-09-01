"""U4 완료조건 검증: 검색 디바운스(프론트 관심사, 여기선 쿼리 파라미터만) · 필터 9종 ·
탭 4종 · 정렬 5종. U2 시드 데이터(120건)를 그대로 사용 — 정확한 개수는 시드 로직이 바뀌면
같이 바뀌므로 하드코딩하지 않고 구조적으로만 검증한다.
"""

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
from app.services.notice_query import SORT_OPTIONS, TABS

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


def test_notices_requires_auth():
    anon = TestClient(app)
    response = anon.get("/api/notices")
    assert response.status_code == 401


def test_notices_list_shape(client: TestClient):
    response = client.get("/api/notices", params={"tab": "all", "size": 5})
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {"items", "total", "page", "size", "tab"}
    assert len(body["items"]) <= 5
    assert body["total"] >= len(body["items"])
    if body["items"]:
        item = body["items"][0]
        assert {"id", "title", "org_name", "stage", "est_price", "close_dt"} <= item.keys()


def test_all_four_tabs_respond(client: TestClient):
    for tab in TABS:
        response = client.get("/api/notices", params={"tab": tab, "size": 1})
        assert response.status_code == 200, tab


def test_untriaged_and_assigned_are_subsets_of_all(client: TestClient):
    all_total = client.get("/api/notices", params={"tab": "all", "size": 1}).json()["total"]
    for tab in ("untriaged", "assigned", "mine"):
        total = client.get("/api/notices", params={"tab": tab, "size": 1}).json()["total"]
        assert total <= all_total


def test_pagination_pages_do_not_overlap(client: TestClient):
    total = client.get("/api/notices", params={"tab": "all", "size": 1}).json()["total"]
    if total < 11:
        pytest.skip("시드 데이터가 페이지 두 장을 채울 만큼 없음")
    page1 = client.get("/api/notices", params={"tab": "all", "size": 10, "page": 1}).json()["items"]
    page2 = client.get("/api/notices", params={"tab": "all", "size": 10, "page": 2}).json()["items"]
    ids1 = {item["id"] for item in page1}
    ids2 = {item["id"] for item in page2}
    assert ids1.isdisjoint(ids2)


def test_search_filters_by_title(client: TestClient):
    response = client.get("/api/notices", params={"tab": "all", "q": "CCTV", "size": 50})
    assert response.status_code == 200
    for item in response.json()["items"]:
        assert "CCTV" in item["title"]


def test_price_range_filter(client: TestClient):
    response = client.get(
        "/api/notices", params={"tab": "all", "price_min": 100_000_000, "price_max": 200_000_000, "size": 50}
    )
    assert response.status_code == 200
    for item in response.json()["items"]:
        if item["est_price"] is not None:
            assert 100_000_000 <= item["est_price"] <= 200_000_000


def test_stage_filter(client: TestClient):
    response = client.get("/api/notices", params={"tab": "all", "stage[]": ["낙찰"], "size": 50})
    assert response.status_code == 200
    for item in response.json()["items"]:
        assert item["stage"] == "낙찰"


@pytest.mark.parametrize("sort", SORT_OPTIONS)
def test_every_sort_option_returns_200(client: TestClient, sort: str):
    response = client.get("/api/notices", params={"tab": "all", "sort": sort, "size": 20})
    assert response.status_code == 200


def test_sort_close_asc_is_ascending(client: TestClient):
    response = client.get("/api/notices", params={"tab": "all", "sort": "close_asc", "status": "open", "size": 50})
    close_dates = [item["close_dt"] for item in response.json()["items"] if item["close_dt"]]
    assert close_dates == sorted(close_dates)


def test_notice_counts_shape(client: TestClient):
    response = client.get("/api/notices/counts")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == set(TABS)
    assert all(count >= 0 for count in body.values())


def test_filter_options_shape(client: TestClient):
    response = client.get("/api/notices/filter-options")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"topics", "orgs", "sources", "stages", "regions"}
    assert len(body["topics"]) > 0
    assert len(body["orgs"]) > 0
