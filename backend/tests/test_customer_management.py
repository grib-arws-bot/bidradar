"""고객 관리 CRUD + 소개서 파일 업로드(2026-09-05) 검증."""

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
from sqlalchemy import select

from app.db import engine
from app.main import app
from app.models import customer

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"

_SAMPLE_PAYLOAD = {
    "name": "[테스트] 고객관리 검증용",
    "plan_tier": "standard",
    "contact_email": "test@example.com",
    "contact_name": "홍길동",
    "contact_title": "팀장",
    "contact_phone": "010-1234-5678",
    "report_recipient_emails": ["a@example.com", "b@example.com"],
    "active": True,
}


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    return c


@pytest.fixture
def temp_customer(client: TestClient):
    response = client.post("/api/customers", json=_SAMPLE_PAYLOAD)
    assert response.status_code == 201
    customer_id = response.json()["id"]
    yield customer_id
    with engine.begin() as conn:
        conn.execute(customer.delete().where(customer.c.id == customer_id))


def test_customers_full_requires_auth():
    response = TestClient(app).get("/api/customers/full")
    assert response.status_code == 401


def test_create_customer_success(client: TestClient, temp_customer: int):
    rows = client.get("/api/customers/full").json()
    row = next(r for r in rows if r["id"] == temp_customer)
    assert row["name"] == _SAMPLE_PAYLOAD["name"]
    assert row["contact_name"] == "홍길동"
    assert row["contact_title"] == "팀장"
    assert row["report_recipient_emails"] == ["a@example.com", "b@example.com"]


def test_update_customer_success(client: TestClient, temp_customer: int):
    updated = dict(_SAMPLE_PAYLOAD, name="[테스트] 이름변경", contact_phone="010-9999-0000")
    response = client.patch(f"/api/customers/{temp_customer}", json=updated)
    assert response.status_code == 200

    rows = client.get("/api/customers/full").json()
    row = next(r for r in rows if r["id"] == temp_customer)
    assert row["name"] == "[테스트] 이름변경"
    assert row["contact_phone"] == "010-9999-0000"


def test_update_customer_404():
    client = TestClient(app)
    client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    response = client.patch("/api/customers/999999999", json=_SAMPLE_PAYLOAD)
    assert response.status_code == 404


def test_delete_customer_success(client: TestClient):
    created = client.post("/api/customers", json=_SAMPLE_PAYLOAD).json()["id"]
    response = client.delete(f"/api/customers/{created}")
    assert response.status_code == 204

    rows = client.get("/api/customers/full").json()
    assert all(r["id"] != created for r in rows)


def test_delete_internal_customer_rejected(client: TestClient):
    rows = client.get("/api/customers/full").json()
    internal_id = next(r["id"] for r in rows if r["plan_tier"] == "internal")
    response = client.delete(f"/api/customers/{internal_id}")
    assert response.status_code == 422


# ---- 소개서 파일 업로드(다중)·다운로드·삭제 -----------------------------------------


def test_upload_list_download_delete_documents(client: TestClient, temp_customer: int):
    files = [
        ("files", ("회사소개서.txt", b"grib company intro", "text/plain")),
        ("files", ("제품소개서.txt", b"product intro content", "text/plain")),
    ]
    upload = client.post(f"/api/customers/{temp_customer}/documents", files=files)
    assert upload.status_code == 201
    docs = upload.json()
    assert len(docs) == 2
    assert {d["filename"] for d in docs} == {"회사소개서.txt", "제품소개서.txt"}

    listed = client.get(f"/api/customers/{temp_customer}/documents").json()
    assert len(listed) == 2

    doc_id = listed[0]["id"]
    download = client.get(f"/api/customers/{temp_customer}/documents/{doc_id}/download")
    assert download.status_code == 200
    assert download.content in (b"grib company intro", b"product intro content")

    delete_resp = client.delete(f"/api/customers/{temp_customer}/documents/{doc_id}")
    assert delete_resp.status_code == 204

    remaining = client.get(f"/api/customers/{temp_customer}/documents").json()
    assert len(remaining) == 1
    assert doc_id not in {d["id"] for d in remaining}


def test_documents_404_for_unknown_customer(client: TestClient):
    response = client.get("/api/customers/999999999/documents")
    assert response.status_code == 404


def test_download_unknown_document_404(client: TestClient, temp_customer: int):
    response = client.get(f"/api/customers/{temp_customer}/documents/999999999/download")
    assert response.status_code == 404
