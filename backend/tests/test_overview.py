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
from sqlalchemy import delete, insert, select

from app.db import engine
from app.main import app
from app.models import notice, source
from app.services.overview import (
    _last_n_months,
    get_ai_processing_overview,
    get_customer_overview,
    get_notice_overview,
    get_ops_overview,
    get_system_overview,
)

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
    assert {"cumulative_daily", "collected_daily"} <= body.keys()
    for key in ("cumulative_daily", "collected_daily"):
        # 최근 14일이 하루도 안 빠지고 다 나와야 한다(수집이 없었던 날도 0으로 채워짐).
        assert len(body[key]["dates"]) == 14
        assert len(body[key]["series"]) > 0
        for s in body[key]["series"]:
            assert len(s["counts"]) == 14
            assert "source_name" in s
        # 소스별 계열 외에 "전체" 합산 계열이 하나 더 있어야 한다(사용자 지시 "소스별과
        # 전체소스를 그려줘").
        assert any(s["source_name"] == "전체" and s["source_id"] is None for s in body[key]["series"])


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


def _series_by_name(series: list[dict], name: str) -> dict:
    return next(s for s in series if s["source_name"] == name)


def test_get_notice_overview_cumulative_total_is_non_decreasing():
    """"전체" 누적 총량은 러닝토탈이라 날짜가 지날수록 줄어들면 안 된다(공고는 삭제돼도
    notice 테이블에서 아예 빠지므로, 이 창 안에서 다시 늘어나는 일은 있어도 줄지는 않는다)."""
    with engine.connect() as conn:
        result = get_notice_overview(conn)
    totals = _series_by_name(result["cumulative_daily"]["series"], "전체")["counts"]
    assert all(totals[i] <= totals[i + 1] for i in range(len(totals) - 1))


def test_get_notice_overview_cumulative_total_equals_sum_of_sources():
    """"전체" 누적 계열은 소스별 누적 계열들의 합과 매 날짜마다 같아야 한다. "임베딩 완료
    누적"(2026-09-17 추가, source_id=None)은 "전체"와 마찬가지로 소스 합산이 아니므로
    source_id로 걸러야 한다 — 이름만으로 거르면 이 계열까지 "소스"로 잘못 합산된다."""
    with engine.connect() as conn:
        result = get_notice_overview(conn)
    series = result["cumulative_daily"]["series"]
    total = _series_by_name(series, "전체")["counts"]
    per_source = [s for s in series if s["source_id"] is not None]
    for i in range(len(total)):
        assert total[i] == sum(s["counts"][i] for s in per_source)


def test_get_notice_overview_embedded_cumulative_series_present_and_non_decreasing():
    """2026-09-17 추가 — "임베딩 완료 누적"은 cumulative_daily에만 있고(collected_daily엔
    없음), 러닝토탈이라 날짜가 지날수록 줄어들면 안 된다."""
    with engine.connect() as conn:
        result = get_notice_overview(conn)
    embedded = _series_by_name(result["cumulative_daily"]["series"], "임베딩 완료 누적")["counts"]
    assert len(embedded) == 14
    assert all(embedded[i] <= embedded[i + 1] for i in range(len(embedded) - 1))
    assert not any(s["source_name"] == "임베딩 완료 누적" for s in result["collected_daily"]["series"])


def test_get_notice_overview_valid_cumulative_excludes_superseded_notices():
    """2026-09-23 사용자 지시 — 전체현황의 "누적 데이터"(9,000대)와 공고 탐색 건수
    (6,000대)가 안 맞는 문제. 원인은 중복 무효화(superseded_by_notice_id) 처리 차이 —
    "유효 공고 누적"은 이 필드가 있는 공고를 빼고 세야 한다. 공유 개발 DB에 이미 다른
    무효화 건이 있을 수 있어(실측 확인됨) 절대값 대신 전/후 델타로 검증한다 — 새 공고
    2건(하나는 다른 하나에 의해 무효화됨)을 넣으면 "전체"는 정확히 +2, "유효"는 무효화
    안 된 것 하나만큼만 +1이어야 한다."""
    with engine.connect() as conn:
        before = get_notice_overview(conn)
    total_before = _series_by_name(before["cumulative_daily"]["series"], "전체")["counts"][-1]
    valid_before = _series_by_name(before["cumulative_daily"]["series"], "유효 공고 누적(중복 제외)")["counts"][-1]

    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()
        latest_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 유효 공고 누적 검증 최신",
                url="https://example.grib-test.kr/notice/valid-cumulative-latest",
            ).returning(notice.c.id)
        ).scalar_one()
        superseded_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 유효 공고 누적 검증 무효화",
                url="https://example.grib-test.kr/notice/valid-cumulative-superseded",
                superseded_by_notice_id=latest_id,
            ).returning(notice.c.id)
        ).scalar_one()
    try:
        with engine.connect() as conn:
            after = get_notice_overview(conn)
        total_after = _series_by_name(after["cumulative_daily"]["series"], "전체")["counts"][-1]
        valid_after = _series_by_name(after["cumulative_daily"]["series"], "유효 공고 누적(중복 제외)")["counts"][-1]
        assert total_after == total_before + 2
        assert valid_after == valid_before + 1
    finally:
        with engine.begin() as conn:
            conn.execute(delete(notice).where(notice.c.id.in_([superseded_id, latest_id])))


def test_get_ai_processing_overview_shape():
    with engine.connect() as conn:
        result = get_ai_processing_overview(conn)
    assert len(result["dates"]) == 14
    names = {s["name"] for s in result["series"]}
    assert names == {"AI분석(A2)", "사업전략 생성"}
    for s in result["series"]:
        assert len(s["counts"]) == 14
        assert all(c >= 0 for c in s["counts"])


def test_get_ops_overview_shape():
    with engine.connect() as conn:
        result = get_ops_overview(conn)
    assert len(result["dates"]) == 14
    names = {s["name"] for s in result["series"]}
    assert names == {"수집 성공", "수집 실패", "리포트 발송"}
    for s in result["series"]:
        assert len(s["counts"]) == 14
        assert all(c >= 0 for c in s["counts"])


def test_overview_ai_processing_requires_auth():
    assert TestClient(app).get("/api/overview/ai-processing").status_code == 401


def test_overview_ops_requires_auth():
    assert TestClient(app).get("/api/overview/ops").status_code == 401


def test_overview_ai_processing_shape(client: TestClient):
    response = client.get("/api/overview/ai-processing")
    assert response.status_code == 200
    body = response.json()
    assert {"dates", "series"} <= body.keys()
    assert len(body["dates"]) == 14


def test_overview_ops_shape(client: TestClient):
    response = client.get("/api/overview/ops")
    assert response.status_code == 200
    body = response.json()
    assert {"dates", "series"} <= body.keys()
    assert len(body["dates"]) == 14


def test_get_notice_overview_collected_total_matches_cumulative_day_over_day_growth():
    """"전체" 수집 건수(그날 신규)는 "전체" 누적 총량의 전날 대비 증가분과 같아야 한다."""
    with engine.connect() as conn:
        result = get_notice_overview(conn)
    cumulative_total = _series_by_name(result["cumulative_daily"]["series"], "전체")["counts"]
    collected_total = _series_by_name(result["collected_daily"]["series"], "전체")["counts"]
    for i in range(1, len(cumulative_total)):
        assert cumulative_total[i] - cumulative_total[i - 1] == collected_total[i]
