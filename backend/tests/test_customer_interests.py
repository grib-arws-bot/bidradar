"""U5b 완료조건 검증: 미리보기=저장 후 실제 건수 · 수집 파이프라인 무영향 · 고객 간 격리."""

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
from sqlalchemy import delete, func, select

from app.db import engine
from app.main import app
from app.models import auth_session, login_attempt, notice, raw_payload, source, source_run

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
def customers(client: TestClient) -> list[dict]:
    return client.get("/api/customers").json()


@pytest.fixture
def customer_b_id(customers: list[dict]) -> int:
    # 시드 데이터의 "예시고객 B"는 관심 프로필이 비어 있음(11절, 빈 상태 확인용) — 격리 테스트의
    # 비교 대상으로 쓰기 좋다.
    standard = [c for c in customers if c["plan_tier"] == "standard"]
    assert len(standard) >= 2
    return standard[1]["id"]


@pytest.fixture
def customer_a_id(customers: list[dict]) -> int:
    standard = [c for c in customers if c["plan_tier"] == "standard"]
    return standard[0]["id"]


def _table_counts(conn) -> dict[str, int]:
    return {
        "notice": conn.execute(select(func.count()).select_from(notice)).scalar_one(),
        "source": conn.execute(select(func.count()).select_from(source)).scalar_one(),
        "source_run": conn.execute(select(func.count()).select_from(source_run)).scalar_one(),
        "raw_payload": conn.execute(select(func.count()).select_from(raw_payload)).scalar_one(),
    }


def test_list_customers_includes_grib(client: TestClient, customers: list[dict]):
    assert any(c["plan_tier"] == "internal" for c in customers)


def test_get_interests_shape(client: TestClient, customer_a_id: int):
    response = client.get(f"/api/customers/{customer_a_id}/interests")
    assert response.status_code == 200
    body = response.json()
    assert {"topic_ids", "terms", "followed_org_ids", "price_min", "price_max", "regions", "topics"} <= body.keys()
    assert len(body["topics"]) > 0


def test_get_interests_404_for_unknown_customer(client: TestClient):
    response = client.get("/api/customers/999999/interests")
    assert response.status_code == 404


def test_preview_matches_saved_actual_count(client: TestClient, customer_b_id: int):
    topics = client.get(f"/api/customers/{customer_b_id}/interests").json()["topics"]
    draft = {"topic_ids": [topics[0]["id"]], "terms": [], "followed_org_ids": [], "regions": []}

    preview = client.post(f"/api/customers/{customer_b_id}/interests/preview", json=draft)
    assert preview.status_code == 200
    preview_count = preview.json()["count"]

    save = client.put(f"/api/customers/{customer_b_id}/interests", json=draft)
    assert save.status_code == 204

    # 저장된 걸 다시 읽어서 같은 초안으로 재조회 — preview와 "저장 후 실제"가 동일한 함수를
    # 거치므로 항상 같아야 한다(U5b 인수조건).
    saved_profile = client.get(f"/api/customers/{customer_b_id}/interests").json()
    actual = client.post(
        f"/api/customers/{customer_b_id}/interests/preview",
        json={
            "topic_ids": saved_profile["topic_ids"],
            "terms": saved_profile["terms"],
            "followed_org_ids": saved_profile["followed_org_ids"],
            "price_min": saved_profile["price_min"],
            "price_max": saved_profile["price_max"],
            "regions": saved_profile["regions"],
        },
    )
    assert actual.json()["count"] == preview_count


def test_save_does_not_touch_collection_pipeline(client: TestClient, customer_a_id: int):
    with engine.connect() as conn:
        before = _table_counts(conn)

    topics = client.get(f"/api/customers/{customer_a_id}/interests").json()["topics"]
    response = client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={"topic_ids": [topics[0]["id"], topics[1]["id"]], "terms": ["CCTV"], "followed_org_ids": [], "regions": []},
    )
    assert response.status_code == 204

    with engine.connect() as conn:
        after = _table_counts(conn)

    assert before == after


def test_customer_isolation(client: TestClient, customer_a_id: int, customer_b_id: int):
    topics = client.get(f"/api/customers/{customer_a_id}/interests").json()["topics"]

    b_before = client.get(f"/api/customers/{customer_b_id}/interests").json()

    response = client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={"topic_ids": [t["id"] for t in topics], "terms": ["영상관제"], "followed_org_ids": [], "regions": []},
    )
    assert response.status_code == 204

    b_after = client.get(f"/api/customers/{customer_b_id}/interests").json()
    assert b_before == b_after


def test_preview_term_counts_present(client: TestClient, customer_a_id: int):
    response = client.post(
        f"/api/customers/{customer_a_id}/interests/preview",
        json={"topic_ids": [], "terms": ["CCTV", "존재하지않는키워드XYZ"], "followed_org_ids": [], "regions": []},
    )
    assert response.status_code == 200
    counts = response.json()["term_counts"]
    assert counts["존재하지않는키워드XYZ"] == 0


def test_saved_search_crud(client: TestClient, customer_a_id: int):
    create = client.post(
        f"/api/customers/{customer_a_id}/searches",
        json={"name": "이번 주 CCTV", "query_params": {"q": "CCTV"}},
    )
    assert create.status_code == 201
    search_id = create.json()["id"]

    listed = client.get(f"/api/customers/{customer_a_id}/searches").json()
    assert any(s["id"] == search_id for s in listed)

    deleted = client.delete(f"/api/customers/{customer_a_id}/searches/{search_id}")
    assert deleted.status_code == 204

    listed_after = client.get(f"/api/customers/{customer_a_id}/searches").json()
    assert not any(s["id"] == search_id for s in listed_after)
