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


# ---- 보고서 메일 자동발송 요일·시간(2026-09-14) -----------------------------------------


def test_email_schedule_requires_auth():
    response = TestClient(app).patch("/api/customers/1/email-schedule", json={"days": [1], "times": ["09:00"]})
    assert response.status_code == 401


def test_email_schedule_update_success_and_round_trips(client: TestClient, temp_customer: int):
    response = client.patch(
        f"/api/customers/{temp_customer}/email-schedule", json={"days": [1, 3, 5], "times": ["09:00"]}
    )
    assert response.status_code == 200
    assert response.json() == {"id": temp_customer, "days": [1, 3, 5], "times": ["09:00"]}

    full = client.get("/api/customers/full").json()
    row = next(c for c in full if c["id"] == temp_customer)
    assert row["report_auto_send_days"] == [1, 3, 5]
    assert row["report_auto_send_times"] == ["09:00"]


def test_email_schedule_accepts_multiple_times(client: TestClient, temp_customer: int):
    # 2026-09-15 사용자 지시 — "메일 발송 시점은 다수개를 지정할 수 있어야 한다."
    response = client.patch(
        f"/api/customers/{temp_customer}/email-schedule",
        json={"days": [1], "times": ["09:00", "13:00", "18:00"]},
    )
    assert response.status_code == 200
    full = client.get("/api/customers/full").json()
    row = next(c for c in full if c["id"] == temp_customer)
    assert row["report_auto_send_times"] == ["09:00", "13:00", "18:00"]


def test_email_schedule_rejects_more_than_three_times(client: TestClient, temp_customer: int):
    response = client.patch(
        f"/api/customers/{temp_customer}/email-schedule",
        json={"days": [1], "times": ["09:00", "10:00", "11:00", "12:00"]},
    )
    assert response.status_code == 422


def test_email_schedule_can_be_cleared(client: TestClient, temp_customer: int):
    client.patch(f"/api/customers/{temp_customer}/email-schedule", json={"days": [2], "times": ["10:00"]})
    response = client.patch(f"/api/customers/{temp_customer}/email-schedule", json={"days": [], "times": []})
    assert response.status_code == 200
    full = client.get("/api/customers/full").json()
    row = next(c for c in full if c["id"] == temp_customer)
    assert row["report_auto_send_days"] == []
    assert row["report_auto_send_times"] == []


def test_email_schedule_rejects_out_of_range_day(client: TestClient, temp_customer: int):
    response = client.patch(f"/api/customers/{temp_customer}/email-schedule", json={"days": [8], "times": ["09:00"]})
    assert response.status_code == 422


def test_email_schedule_rejects_duplicate_days(client: TestClient, temp_customer: int):
    response = client.patch(
        f"/api/customers/{temp_customer}/email-schedule", json={"days": [1, 1], "times": ["09:00"]}
    )
    assert response.status_code == 422


def test_email_schedule_rejects_days_without_times(client: TestClient, temp_customer: int):
    response = client.patch(f"/api/customers/{temp_customer}/email-schedule", json={"days": [1], "times": []})
    assert response.status_code == 422


def test_email_schedule_rejects_times_without_days(client: TestClient, temp_customer: int):
    response = client.patch(f"/api/customers/{temp_customer}/email-schedule", json={"days": [], "times": ["09:00"]})
    assert response.status_code == 422


def test_email_schedule_rejects_bad_time_format(client: TestClient, temp_customer: int):
    response = client.patch(
        f"/api/customers/{temp_customer}/email-schedule", json={"days": [1], "times": ["not-a-time"]}
    )
    assert response.status_code == 422


def test_email_schedule_404_for_unknown_customer(client: TestClient):
    response = client.patch("/api/customers/999999/email-schedule", json={"days": [1], "times": ["09:00"]})
    assert response.status_code == 404


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
    body = upload.json()
    assert body["errors"] == []
    docs = body["documents"]
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


def test_upload_partial_failure_keeps_valid_files(client: TestClient, temp_customer: int):
    """파일 하나가 용량 초과라도(2026-09-11 수정 전엔 트랜잭션 전체가 롤백돼 정상 파일까지
    안 올라갔다) 나머지 정상 파일은 저장되고, 실패 사유는 errors로 그대로 보고된다."""
    from app.services.customer_management import MAX_DOCUMENT_BYTES

    files = [
        ("files", ("정상.txt", b"ok content", "text/plain")),
        ("files", ("너무큼.txt", b"x" * (MAX_DOCUMENT_BYTES + 1), "text/plain")),
    ]
    upload = client.post(f"/api/customers/{temp_customer}/documents", files=files)
    assert upload.status_code == 201
    body = upload.json()
    assert len(body["errors"]) == 1
    assert "너무큼.txt" in body["errors"][0]
    assert [d["filename"] for d in body["documents"]] == ["정상.txt"]


def test_upload_all_files_fail_returns_422(client: TestClient, temp_customer: int):
    from app.services.customer_management import MAX_DOCUMENT_BYTES

    files = [("files", ("너무큼.txt", b"x" * (MAX_DOCUMENT_BYTES + 1), "text/plain"))]
    upload = client.post(f"/api/customers/{temp_customer}/documents", files=files)
    assert upload.status_code == 422


def test_list_documents_orders_same_timestamp_files_by_id_desc(client: TestClient, temp_customer: int):
    """uploaded_at은 트랜잭션 시작 시각이라 한 번에 여러 파일을 올리면 값이 동일하다
    (2026-09-11 사용자 발견 — 방금 올린 파일이 안 보이는 것처럼 느껴짐). id를 보조
    정렬키로 둬 항상 최신 업로드가 위로 오게 한다."""
    files = [
        ("files", ("첫번째.txt", b"1", "text/plain")),
        ("files", ("두번째.txt", b"2", "text/plain")),
        ("files", ("세번째.txt", b"3", "text/plain")),
    ]
    client.post(f"/api/customers/{temp_customer}/documents", files=files)
    listed = client.get(f"/api/customers/{temp_customer}/documents").json()
    ids = [d["id"] for d in listed]
    assert ids == sorted(ids, reverse=True)


def test_reference_urls_round_trip(client: TestClient, temp_customer: int):
    payload = dict(_SAMPLE_PAYLOAD, reference_urls=["https://example.com", "https://grib.co.kr"])
    response = client.patch(f"/api/customers/{temp_customer}", json=payload)
    assert response.status_code == 200

    rows = client.get("/api/customers/full").json()
    row = next(r for r in rows if r["id"] == temp_customer)
    assert row["reference_urls"] == ["https://example.com", "https://grib.co.kr"]


def test_documents_404_for_unknown_customer(client: TestClient):
    response = client.get("/api/customers/999999999/documents")
    assert response.status_code == 404


def test_download_unknown_document_404(client: TestClient, temp_customer: int):
    response = client.get(f"/api/customers/{temp_customer}/documents/999999999/download")
    assert response.status_code == 404
