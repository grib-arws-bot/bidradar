"""공고 탐색 제목 제외 키워드(notice_title_exclude_word) 관리자 CRUD 검증(2026-09-13).

conftest.py의 트랜잭션 격리 덕분에(2026-09-13 도입) 이 테스트들은 명시적 cleanup이 필요
없다 — 각 테스트가 만든 INSERT/DELETE는 테스트 종료 시 자동 롤백된다.
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

from app.db import engine
from app.main import app
from app.services.notice_exclude_words import create_exclude_word, delete_exclude_word, list_exclude_words

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    return c


def test_exclude_words_requires_auth():
    assert TestClient(app).get("/api/admin/notice-exclude-words").status_code == 401


def test_create_and_list_exclude_word(client: TestClient):
    response = client.post("/api/admin/notice-exclude-words", json={"term": "감리"})
    assert response.status_code == 201
    assert response.json()["term"] == "감리"

    listed = client.get("/api/admin/notice-exclude-words").json()
    assert any(w["term"] == "감리" for w in listed)


def test_create_rejects_empty_term(client: TestClient):
    response = client.post("/api/admin/notice-exclude-words", json={"term": "   "})
    assert response.status_code == 400


def test_create_rejects_duplicate_term(client: TestClient):
    first = client.post("/api/admin/notice-exclude-words", json={"term": "모집"})
    assert first.status_code == 201
    second = client.post("/api/admin/notice-exclude-words", json={"term": "모집"})
    assert second.status_code == 400


def test_delete_exclude_word(client: TestClient):
    created = client.post("/api/admin/notice-exclude-words", json={"term": "고도화"}).json()
    delete_response = client.delete(f"/api/admin/notice-exclude-words/{created['id']}")
    assert delete_response.status_code == 204

    listed = client.get("/api/admin/notice-exclude-words").json()
    assert not any(w["id"] == created["id"] for w in listed)


def test_delete_unknown_word_404(client: TestClient):
    response = client.delete("/api/admin/notice-exclude-words/999999")
    assert response.status_code == 404


def test_service_functions_directly():
    with engine.begin() as conn:
        row = create_exclude_word(conn, "유지보수")
        assert row["term"] == "유지보수"
        words = list_exclude_words(conn)
        assert any(w["id"] == row["id"] for w in words)
        assert delete_exclude_word(conn, row["id"]) is True
        assert delete_exclude_word(conn, row["id"]) is False  # 이미 지운 것 — 두 번째는 False
