"""소스 관리 목록(관리자 페이지) 검증."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")
os.environ.setdefault("ADMIN_EMAIL", "report@grib.co.kr")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$argon2id$v=19$m=65536,t=3,p=4$9/7/Wg+VSkOsVCeiQiCz7w$bdDzJi9bKuERjBb6NHN0Ztk+X6uwxugL7kViHVRiqnY",
)

from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import engine
from app.main import app
from app.models import audit_log, org, source

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"


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
    assert {
        "id", "name", "org_name", "homepage_url", "adapter_type", "adapter_label", "stage", "status", "last_run_at",
        "legal_tier", "legal_verified_at", "compliance_overdue", "auto_extract", "auto_analyze", "active",
        "notice_type", "schedule_times",
    } <= row.keys()
    assert row["legal_tier"] in {"A", "B", "C"}
    assert isinstance(row["auto_extract"], bool)
    assert isinstance(row["auto_analyze"], bool)
    assert isinstance(row["active"], bool)
    assert row["notice_type"] in ("공공입찰", "정부지원")
    assert isinstance(row["schedule_times"], list)

    # 기관별로 묶여 있어야 한다 — DB 콜레이션이 파이썬 sorted()와 한글 정렬 기준이 다를 수 있어
    # 정확한 알파벳 순서 대신 "같은 기관명이 떨어져서 두 번 나타나지 않는지"만 확인한다
    named = [r["org_name"] for r in rows if r["org_name"] is not None]
    grouped_once = []
    for org_name in named:
        if not grouped_once or grouped_once[-1] != org_name:
            grouped_once.append(org_name)
    assert len(grouped_once) == len(set(named))


def test_sources_status_is_one_of_known_values(client: TestClient):
    # "running"(2026-09-08 신설) — "지금 수집" 진행 중 표시용, 정상 값의 하나.
    rows = client.get("/api/admin/sources").json()
    for row in rows:
        assert row["status"] in {"ok", "warn", "fail", "inactive", "no_run_yet", "running"}


# ---- 발주기관(agency) 중심 목록 — 2026-09-01 요청 ---------------------------------


def test_agencies_requires_auth():
    response = TestClient(app).get("/api/admin/sources/agencies")
    assert response.status_code == 401


def test_agencies_list_shape_and_hangul_first_sort(client: TestClient):
    response = client.get("/api/admin/sources/agencies")
    assert response.status_code == 200
    body = response.json()
    assert {"items", "total", "page", "size"} <= body.keys()
    rows = body["items"]
    assert len(rows) > 0
    assert body["total"] >= len(rows)

    row = rows[0]
    assert {
        "id", "name", "abbr", "category", "channel_url", "channel", "adapter_label", "status", "last_run_at",
        "legal_tier", "legal_verified_at", "compliance_overdue",
    } <= row.keys()

    # IRIS(공고기관/채널이지 발주기관이 아님)는 이 목록에 나오면 안 된다. "조달청"은 한때
    # 여기서도 안 나왔지만(채널명일 뿐이라) 나라장터 우수조달물품 제3자단가계약처럼 조달청
    # 자신이 실제 발주기관인 실공고가 있어(2026-09-04 실데이터로 확인) 더 이상 배제 대상이
    # 아니다 — org 테이블에 정당하게 들어올 수 있는 이름이다.
    names = [r["name"] for r in rows]
    assert "IRIS" not in names

    # 한글 이름이 영어 이름보다 먼저 나와야 한다(2026-09-01 요청)
    is_hangul = [bool(r["name"]) and "가" <= r["name"][0] <= "힣" for r in rows]
    first_non_hangul = next((i for i, v in enumerate(is_hangul) if not v), len(is_hangul))
    assert all(is_hangul[:first_non_hangul])
    assert not any(is_hangul[first_non_hangul:])


def test_agencies_search_by_abbr(client: TestClient):
    rows = client.get("/api/admin/sources/agencies", params={"q": "NIPA"}).json()["items"]
    assert len(rows) == 1
    assert rows[0]["name"] == "정보통신산업진흥원"


def test_agencies_filter_by_status_no_source(client: TestClient):
    # 2026-09-01 seed 당시 KOCCA는 소속 소스가 없어 이 테스트가 실데이터(KOCCA)에 직접 의존했는데,
    # 이후 실제로 KOCCA용 소스가 연결되면서(2026-09 자체조달 갭분석 작업) 실패했다 — 이 DB는
    # conftest.py 설명대로 격리된 테스트 DB가 아니라 계속 바뀌는 실 dev DB라 특정 실제 기관명에
    # 의존하면 안 된다. 이 테스트만을 위한 임시 org(소스 없음)를 만들어 격리한다.
    with engine.begin() as conn:
        temp_id = conn.execute(
            org.insert().values(name="_테스트전용무소속기관", code="ORGTEST_NOSRC", abbr="ZZTESTNOSRC", source_id=None)
        ).inserted_primary_key[0]
    try:
        rows = client.get("/api/admin/sources/agencies", params={"q": "ZZTESTNOSRC"}).json()["items"]
        assert len(rows) == 1
        assert rows[0]["status"] == "no_source"
        assert rows[0]["channel"] is None

        filtered = client.get("/api/admin/sources/agencies", params={"status": "no_source", "size": 100}).json()["items"]
        assert any(r["abbr"] == "ZZTESTNOSRC" for r in filtered)
        assert all(r["status"] == "no_source" for r in filtered)
    finally:
        with engine.begin() as conn:
            conn.execute(org.delete().where(org.c.id == temp_id))


def test_agencies_pagination_second_page_is_disjoint(client: TestClient):
    first = client.get("/api/admin/sources/agencies", params={"size": 20, "page": 1}).json()
    second = client.get("/api/admin/sources/agencies", params={"size": 20, "page": 2}).json()
    assert first["total"] == second["total"]
    first_ids = {r["id"] for r in first["items"]}
    second_ids = {r["id"] for r in second["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_agency_categories_route(client: TestClient):
    categories = client.get("/api/admin/sources/agencies/categories").json()
    assert isinstance(categories, list)
    assert len(categories) > 0
    assert categories == sorted(categories)


# ---- 첨부문서 자동 분석 토글(2026-09-04, S8 A1 auto_extract) -----------------------


@pytest.fixture
def _restore_auto_extract():
    """토글 대상 소스의 auto_extract 원래 값을 기억해뒀다가 테스트 후 되돌린다 —
    공유 개발 DB라 실제 IRIS 설정(auto_extract=true)을 테스트가 영구히 바꾸면 안 된다."""
    with engine.connect() as conn:
        source_id = conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()
        original = conn.execute(select(source.c.auto_extract).where(source.c.id == source_id)).scalar_one()
    yield source_id, original
    with engine.begin() as conn:
        conn.execute(source.update().where(source.c.id == source_id).values(auto_extract=original))
        conn.execute(
            audit_log.delete().where(audit_log.c.target_type == "source", audit_log.c.target_id == str(source_id))
        )


def test_auto_extract_requires_auth():
    response = TestClient(app).patch("/api/admin/sources/1/auto-extract", json={"auto_extract": True})
    assert response.status_code == 401


def test_auto_extract_update_success_and_audit_logged(client: TestClient, _restore_auto_extract):
    source_id, original = _restore_auto_extract
    toggled = not original

    response = client.patch(f"/api/admin/sources/{source_id}/auto-extract", json={"auto_extract": toggled})
    assert response.status_code == 200
    assert response.json() == {"id": source_id, "auto_extract": toggled}

    rows = client.get("/api/admin/sources").json()
    row = next(r for r in rows if r["id"] == source_id)
    assert row["auto_extract"] == toggled

    with engine.connect() as conn:
        detail = conn.execute(
            select(audit_log.c.detail)
            .where(audit_log.c.target_type == "source", audit_log.c.target_id == str(source_id))
            .order_by(audit_log.c.id.desc())
            .limit(1)
        ).scalar_one()
    assert detail == {"auto_extract": toggled}


# ---- 공고 자동 수집 on/off 토글(2026-09-05) ---------------------------------------


@pytest.fixture
def _restore_active():
    """auto_extract 토글과 같은 이유로 원래 값을 되돌린다 — 공유 개발 DB의 실제 활성/비활성
    설정(2026-09-05 사용자 지정)을 테스트가 영구히 바꾸면 안 된다."""
    with engine.connect() as conn:
        source_id = conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()
        original = conn.execute(select(source.c.active).where(source.c.id == source_id)).scalar_one()
    yield source_id, original
    with engine.begin() as conn:
        conn.execute(source.update().where(source.c.id == source_id).values(active=original))
        conn.execute(
            audit_log.delete().where(audit_log.c.target_type == "source", audit_log.c.target_id == str(source_id))
        )


def test_active_toggle_requires_auth():
    response = TestClient(app).patch("/api/admin/sources/1/active", json={"active": True})
    assert response.status_code == 401


def test_active_toggle_update_success_and_audit_logged(client: TestClient, _restore_active):
    source_id, original = _restore_active
    toggled = not original

    response = client.patch(f"/api/admin/sources/{source_id}/active", json={"active": toggled})
    assert response.status_code == 200
    assert response.json() == {"id": source_id, "active": toggled}

    rows = client.get("/api/admin/sources").json()
    row = next(r for r in rows if r["id"] == source_id)
    assert row["active"] == toggled

    with engine.connect() as conn:
        detail = conn.execute(
            select(audit_log.c.detail)
            .where(audit_log.c.target_type == "source", audit_log.c.target_id == str(source_id))
            .order_by(audit_log.c.id.desc())
            .limit(1)
        ).scalar_one()
    assert detail == {"active": toggled}


# ---- AI 자동분석(A2, Haiku) on/off 토글(2026-09-05) -------------------------------


@pytest.fixture
def _restore_auto_analyze():
    """active/auto_extract 토글과 같은 이유로 원래 값을 되돌린다."""
    with engine.connect() as conn:
        source_id = conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()
        original = conn.execute(select(source.c.auto_analyze).where(source.c.id == source_id)).scalar_one()
    yield source_id, original
    with engine.begin() as conn:
        conn.execute(source.update().where(source.c.id == source_id).values(auto_analyze=original))
        conn.execute(
            audit_log.delete().where(audit_log.c.target_type == "source", audit_log.c.target_id == str(source_id))
        )


def test_auto_analyze_toggle_requires_auth():
    response = TestClient(app).patch("/api/admin/sources/1/auto-analyze", json={"auto_analyze": True})
    assert response.status_code == 401


def test_auto_analyze_toggle_update_success_and_audit_logged(client: TestClient, _restore_auto_analyze):
    source_id, original = _restore_auto_analyze
    toggled = not original

    response = client.patch(f"/api/admin/sources/{source_id}/auto-analyze", json={"auto_analyze": toggled})
    assert response.status_code == 200
    assert response.json() == {"id": source_id, "auto_analyze": toggled}

    rows = client.get("/api/admin/sources").json()
    row = next(r for r in rows if r["id"] == source_id)
    assert row["auto_analyze"] == toggled

    with engine.connect() as conn:
        detail = conn.execute(
            select(audit_log.c.detail)
            .where(audit_log.c.target_type == "source", audit_log.c.target_id == str(source_id))
            .order_by(audit_log.c.id.desc())
            .limit(1)
        ).scalar_one()
    assert detail == {"auto_analyze": toggled}


# ---- 공고 업데이트 시간 설정(2026-09-05, 설정 UI만 — 실행 엔진은 다음 작업) -------------------


@pytest.fixture
def _restore_schedule_times():
    with engine.connect() as conn:
        source_id = conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()
        original = conn.execute(select(source.c.schedule_times).where(source.c.id == source_id)).scalar_one()
    yield source_id, original
    with engine.begin() as conn:
        conn.execute(source.update().where(source.c.id == source_id).values(schedule_times=original))
        conn.execute(
            audit_log.delete().where(audit_log.c.target_type == "source", audit_log.c.target_id == str(source_id))
        )


def test_schedule_times_requires_auth():
    response = TestClient(app).patch("/api/admin/sources/1/schedule", json={"schedule_times": ["09:00"]})
    assert response.status_code == 401


def test_schedule_times_update_success_and_audit_logged(client: TestClient, _restore_schedule_times):
    source_id, _original = _restore_schedule_times
    new_times = ["09:00", "13:30"]

    response = client.patch(f"/api/admin/sources/{source_id}/schedule", json={"schedule_times": new_times})
    assert response.status_code == 200
    assert response.json() == {"id": source_id, "schedule_times": new_times}

    rows = client.get("/api/admin/sources").json()
    row = next(r for r in rows if r["id"] == source_id)
    assert row["schedule_times"] == new_times

    with engine.connect() as conn:
        detail = conn.execute(
            select(audit_log.c.detail)
            .where(audit_log.c.target_type == "source", audit_log.c.target_id == str(source_id))
            .order_by(audit_log.c.id.desc())
            .limit(1)
        ).scalar_one()
    assert detail == {"schedule_times": new_times}


def test_schedule_times_allows_partial_and_empty(client: TestClient, _restore_schedule_times):
    source_id, _original = _restore_schedule_times

    one_only = client.patch(f"/api/admin/sources/{source_id}/schedule", json={"schedule_times": ["18:45"]})
    assert one_only.status_code == 200

    cleared = client.patch(f"/api/admin/sources/{source_id}/schedule", json={"schedule_times": []})
    assert cleared.status_code == 200
    assert cleared.json()["schedule_times"] == []


def test_schedule_times_rejects_more_than_three(client: TestClient, _restore_schedule_times):
    source_id, _original = _restore_schedule_times
    response = client.patch(
        f"/api/admin/sources/{source_id}/schedule",
        json={"schedule_times": ["09:00", "12:00", "15:00", "18:00"]},
    )
    assert response.status_code == 422


def test_schedule_times_allows_any_minute(client: TestClient, _restore_schedule_times):
    # 드롭다운(5분 단위)에서 직접 입력(HH:MM)으로 바뀌면서(2026-09-07) 5분 단위 제한은 뺐다.
    source_id, _original = _restore_schedule_times
    response = client.patch(f"/api/admin/sources/{source_id}/schedule", json={"schedule_times": ["09:03"]})
    assert response.status_code == 200
    assert response.json()["schedule_times"] == ["09:03"]


def test_schedule_times_rejects_out_of_range_hour(client: TestClient, _restore_schedule_times):
    source_id, _original = _restore_schedule_times
    response = client.patch(f"/api/admin/sources/{source_id}/schedule", json={"schedule_times": ["24:00"]})
    assert response.status_code == 422


def test_schedule_times_rejects_bad_format(client: TestClient, _restore_schedule_times):
    source_id, _original = _restore_schedule_times
    response = client.patch(f"/api/admin/sources/{source_id}/schedule", json={"schedule_times": ["not-a-time"]})
    assert response.status_code == 422


def test_run_source_rejects_inactive_source():
    # adapter_type=openapi·legal_tier=B가 확실한 소스로 골라야 active 검사보다 먼저 걸리는
    # 다른 ValueError(어댑터 타입 등)와 섞이지 않는다. run_source()를 직접 부르므로(래퍼를
    # 안 거침) source_run에 아무 행도 안 남는다(inactive 검사가 fetch 시도보다 먼저 걸림).
    from app.collector.runner import run_source
    from app.db import engine as _engine

    with _engine.begin() as conn:
        source_id = conn.execute(
            select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")
        ).scalar_one()
        conn.execute(source.update().where(source.c.id == source_id).values(active=False))
    try:
        with _engine.begin() as conn:
            with pytest.raises(ValueError, match="비활성화"):
                run_source(conn, source_id)
    finally:
        with _engine.begin() as conn:
            conn.execute(source.update().where(source.c.id == source_id).values(active=True))


def test_auto_extract_unknown_source_404(client: TestClient):
    response = client.patch("/api/admin/sources/999999/auto-extract", json={"auto_extract": True})
    assert response.status_code == 404


# ---- 지금 수집(스케줄 무관 즉시 1회 수집, 2026-09-07) -----------------------------


def test_collect_now_requires_auth():
    response = TestClient(app).post("/api/admin/sources/1/collect-now")
    assert response.status_code == 401


def test_collect_now_rejects_inactive_source(client: TestClient):
    # 실제 외부 API를 안 건드리고 검증 경로만 확인 — active 검사가 fetch보다 먼저 걸린다.
    # run_source_and_process_pending()는(2026-09-08부터) run_source를 부르기 전에 이미
    # 'running' 행을 남기므로, inactive로 실패해도 'fail' 행이 하나 생긴다 — 정리해준다.
    from app.models import source_run

    with engine.begin() as conn:
        source_id = conn.execute(
            select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")
        ).scalar_one()
        conn.execute(source.update().where(source.c.id == source_id).values(active=False))
    try:
        response = client.post(f"/api/admin/sources/{source_id}/collect-now")
        assert response.status_code == 422
        assert "비활성화" in response.json()["detail"]
    finally:
        with engine.begin() as conn:
            conn.execute(source.update().where(source.c.id == source_id).values(active=True))
            conn.execute(
                source_run.delete().where(
                    source_run.c.source_id == source_id, source_run.c.error_message.like("%비활성화%")
                )
            )


def test_collect_now_rejects_when_already_running(client: TestClient):
    # 2026-09-08 — 동시 실행 방지(CollectionInProgressError → 409). 사용자가 "지금 수집"
    # 클릭 후 다른 메뉴로 갔다 돌아오면 이미 끝난 것처럼 보이던 문제의 짝 — 서버가 실제로
    # 진행 중이면 두 번째 요청을 명확히 거부해야 한다.
    from app.models import source_run

    with engine.begin() as conn:
        source_id = conn.execute(
            select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")
        ).scalar_one()
        run_id = conn.execute(
            source_run.insert().values(source_id=source_id, status="running", items_fetched=0).returning(source_run.c.id)
        ).scalar_one()
    try:
        response = client.post(f"/api/admin/sources/{source_id}/collect-now")
        assert response.status_code == 409
        assert "진행 중" in response.json()["detail"]
    finally:
        with engine.begin() as conn:
            conn.execute(source_run.delete().where(source_run.c.id == run_id))


def test_collect_now_success_records_audit_log(client: TestClient):
    # 실제 data.go.kr 호출·첨부분석·AI분석은 mock으로 대체 — 네트워크 성패와 무관하게
    # 라우터·감사로그 배선만 검증한다(app.services.customer_interest.py의 A1 mock 패턴과 동일).
    fake_result = {
        "fetched": 3, "inserted": 1, "skipped": 0, "scored": 1, "out_of_window": 0,
        "already_closed": 2, "dedup_groups_with_duplicates": 0, "dedup_notices_updated": 0,
        "extraction_candidates": 1, "auto_extracted": 1, "analyze_candidates": 0, "auto_analyzed": 0,
    }
    with engine.connect() as conn:
        source_id = conn.execute(
            select(source.c.id).where(source.c.name == "나라장터 입찰공고정보서비스(용역)")
        ).scalar_one()

    with mock.patch("app.api.sources.run_source_and_process_pending", return_value=fake_result) as mock_run:
        response = client.post(f"/api/admin/sources/{source_id}/collect-now")
    assert response.status_code == 200
    assert response.json() == {"id": source_id, **fake_result}
    assert mock_run.call_args.kwargs == {}

    with engine.connect() as conn:
        detail = conn.execute(
            select(audit_log.c.detail, audit_log.c.action)
            .where(audit_log.c.target_type == "source", audit_log.c.target_id == str(source_id))
            .order_by(audit_log.c.id.desc())
            .limit(1)
        ).one()
    assert detail.action == "source.collect_now"
    assert detail.detail == fake_result

    with engine.begin() as conn:
        conn.execute(
            audit_log.delete().where(audit_log.c.target_type == "source", audit_log.c.target_id == str(source_id))
        )
