"""관리자 홈 대시보드(2026-09-12 재설계 — 고객 현황/시스템 현황/공고 데이터 3카드) 검증."""

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
from app.services.overview import _last_n_months, get_customer_overview, get_notice_overview, get_system_overview

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    return c


def test_overview_customers_requires_auth():
    assert TestClient(app).get("/api/overview/customers").status_code == 401


def test_overview_system_requires_auth():
    assert TestClient(app).get("/api/overview/system").status_code == 401


def test_overview_notices_requires_auth():
    assert TestClient(app).get("/api/overview/notices").status_code == 401


def test_overview_customers_shape(client: TestClient):
    response = client.get("/api/overview/customers")
    assert response.status_code == 200
    body = response.json()
    assert body["total_customers"] > 0
    assert {"months", "customer_total", "reports_generated", "reports_sent"} <= body["monthly"].keys()
    assert len(body["monthly"]["months"]) == 6
    assert len(body["monthly"]["customer_total"]) == 6
    assert isinstance(body["recent_reports"], list)


def test_overview_system_shape(client: TestClient):
    response = client.get("/api/overview/system")
    assert response.status_code == 200
    body = response.json()
    assert {"resources", "llm_usage", "channels"} <= body.keys()
    # 개발 PC(Windows, 컨테이너 밖)에선 /proc·cgroup이 없어 available=False로 응답한다 —
    # 실제 리눅스 컨테이너 안에서의 값 자체는 test_system_resources.py가 모킹으로 검증한다.
    assert "available" in body["resources"]
    if body["resources"]["available"]:
        assert {"cpu", "memory", "disk"} <= body["resources"].keys()
        # BidRadar 자체 디스크 사용량(pg_database_size) — 2026-09-12, DB가 살아있는 한 항상 채워짐.
        assert body["resources"]["disk"]["app_used_bytes"] > 0
    assert {"total_calls", "total_tokens", "total_cost_usd", "breakdown"} <= body["llm_usage"].keys()
    # 수집 대상만(schedule_times가 있는 소스) — 실제 운영 중인 5개 소스만 나와야 하고,
    # 15개 전체 소스가 다 나오면 안 됨(수집 안 하는 소스까지 섞이는 회귀 방지).
    assert 0 < len(body["channels"]) < 15


def test_overview_notices_shape(client: TestClient):
    response = client.get("/api/overview/notices")
    assert response.status_code == 200
    body = response.json()
    assert {"cumulative", "daily"} <= body.keys()
    assert len(body["cumulative"]) > 0
    for row in body["cumulative"]:
        assert row["total"] == row["ai_analyzed"] + row["extracted_only"] + row["unanalyzed"]
        assert "source_name" in row
    # 최근 14일이 하루도 안 빠지고 다 나와야 한다(수집이 없었던 날도 0으로 채워짐).
    assert len(body["daily"]) == 14
    for row in body["daily"]:
        assert row["total"] == row["ai_analyzed"] + row["extracted_only"] + row["unanalyzed"]
        assert "date" in row


def test_last_n_months_returns_six_consecutive_months_ending_this_month():
    from datetime import datetime, timezone

    months = _last_n_months(6)
    assert len(months) == 6
    assert months[-1] == datetime.now(timezone.utc).strftime("%Y-%m")
    assert months == sorted(months)  # 오래된 순


def test_get_customer_overview_monthly_totals_are_non_decreasing():
    """고객 수는 누적(생성만 되고 삭제 안 됨)이라 월이 지날수록 줄어들면 안 된다."""
    with engine.connect() as conn:
        result = get_customer_overview(conn)
    totals = result["monthly"]["customer_total"]
    assert all(totals[i] <= totals[i + 1] for i in range(len(totals) - 1))


def test_get_system_overview_returns_llm_and_resources():
    with engine.connect() as conn:
        result = get_system_overview(conn)
    assert "available" in result["resources"]  # 개발 PC에선 False, 실제 컨테이너에선 True
    assert result["llm_usage"]["total_calls"] >= 0


def test_get_notice_overview_daily_total_is_subset_of_cumulative():
    """하루치(전체 소스 합산) total이 모든 소스를 합친 누적 total보다 클 수는 없다."""
    with engine.connect() as conn:
        result = get_notice_overview(conn)
    cumulative_total = sum(r["total"] for r in result["cumulative"])
    for row in result["daily"]:
        assert row["total"] <= cumulative_total
