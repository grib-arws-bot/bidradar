"""공고별 자격요건 판정 조회 + 목록 필터 검증 (app/services/notice_eligibility.py)."""

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
from app.models import analysis, analysis_eligibility, customer, notice, source
from app.services.notice_eligibility import filter_notice_ids_by_eligibility, get_eligibility_verdict

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    return c


def _any_source_id(conn) -> int:
    return conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()


@pytest.fixture
def temp_customer():
    with engine.begin() as conn:
        customer_id = conn.execute(
            insert(customer).values(name="[테스트] 자격판정 검증용 고객", plan_tier="standard").returning(customer.c.id)
        ).scalar_one()
    yield customer_id
    with engine.begin() as conn:
        conn.execute(delete(customer).where(customer.c.id == customer_id))


def _make_notice_with_eligibility(conn, *, axes: dict | None) -> int:
    notice_id = conn.execute(
        insert(notice).values(
            source_id=_any_source_id(conn), source_ver=1, stage="입찰공고", title="[테스트] 자격판정 검증용 공고",
            url=f"https://example.grib-test.kr/notice/eligibility-{id(object())}",
        ).returning(notice.c.id)
    ).scalar_one()
    analysis_id = conn.execute(
        insert(analysis).values(notice_id=notice_id, source_kind="notice", input_ref="x", status="done", ver=1)
        .returning(analysis.c.id)
    ).scalar_one()
    if axes is not None:
        conn.execute(insert(analysis_eligibility).values(analysis_id=analysis_id, **axes))
    return notice_id


def _cleanup(notice_ids: list[int]) -> None:
    with engine.begin() as conn:
        # analysis.notice_id는 ondelete 지정이 없어(cascade 아님) notice보다 먼저 지워야 한다 —
        # analysis_eligibility는 analysis_id CASCADE라 analysis 삭제로 같이 지워짐.
        conn.execute(delete(analysis).where(analysis.c.notice_id.in_(notice_ids)))
        conn.execute(delete(notice).where(notice.c.id.in_(notice_ids)))


_ALL_NO_RESTRICTION = {
    "company_size_allowed_tiers": [], "company_size_cite": None,
    "research_institute_required": False, "research_institute_cite": None,
    "venture_cert_required": False, "venture_cert_cite": None,
    "industry_codes_required": [], "industry_codes_cite": None,
    "certifications_required": [], "certifications_cite": None,
}


def test_get_eligibility_verdict_none_when_no_analysis_eligibility_row(temp_customer: int):
    with engine.begin() as conn:
        notice_id = _make_notice_with_eligibility(conn, axes=None)
    try:
        with engine.connect() as conn:
            assert get_eligibility_verdict(conn, temp_customer, notice_id) is None
    finally:
        _cleanup([notice_id])


def test_get_eligibility_verdict_ok_when_all_axes_unrestricted(temp_customer: int):
    with engine.begin() as conn:
        notice_id = _make_notice_with_eligibility(conn, axes=_ALL_NO_RESTRICTION)
    try:
        with engine.connect() as conn:
            verdict = get_eligibility_verdict(conn, temp_customer, notice_id)
        assert verdict["overall"] == "ok"
        assert all(axis["judgement"] == "ok" for axis in verdict["axes"].values())
    finally:
        _cleanup([notice_id])


def test_get_eligibility_verdict_no_when_company_size_mismatch(temp_customer: int):
    axes = dict(_ALL_NO_RESTRICTION, company_size_allowed_tiers=["대기업"], company_size_cite="제2장 (1)")
    with engine.begin() as conn:
        notice_id = _make_notice_with_eligibility(conn, axes=axes)
        conn.execute(customer.update().where(customer.c.id == temp_customer).values(eligibility_company_size_tier="중소기업"))
    try:
        with engine.connect() as conn:
            verdict = get_eligibility_verdict(conn, temp_customer, notice_id)
        assert verdict["overall"] == "no"
        assert verdict["axes"]["company_size"]["judgement"] == "no"
        assert verdict["axes"]["company_size"]["cite"] == "제2장 (1)"
    finally:
        _cleanup([notice_id])


def test_get_eligibility_verdict_unknown_when_customer_profile_empty(temp_customer: int):
    axes = dict(_ALL_NO_RESTRICTION, company_size_allowed_tiers=["중소기업"], company_size_cite="제2장 (1)")
    with engine.begin() as conn:
        notice_id = _make_notice_with_eligibility(conn, axes=axes)
    try:
        with engine.connect() as conn:
            verdict = get_eligibility_verdict(conn, temp_customer, notice_id)
        assert verdict["overall"] == "unknown"  # 자사 기업규모 미입력
    finally:
        _cleanup([notice_id])


def test_filter_notice_ids_by_eligibility_returns_matching_status(temp_customer: int):
    ok_axes = _ALL_NO_RESTRICTION
    no_axes = dict(_ALL_NO_RESTRICTION, company_size_allowed_tiers=["대기업"], company_size_cite="제2장 (1)")
    with engine.begin() as conn:
        ok_notice_id = _make_notice_with_eligibility(conn, axes=ok_axes)
        no_notice_id = _make_notice_with_eligibility(conn, axes=no_axes)
        conn.execute(customer.update().where(customer.c.id == temp_customer).values(eligibility_company_size_tier="중소기업"))
    try:
        with engine.connect() as conn:
            matched_ok = filter_notice_ids_by_eligibility(conn, [ok_notice_id, no_notice_id], temp_customer, "ok")
            matched_no = filter_notice_ids_by_eligibility(conn, [ok_notice_id, no_notice_id], temp_customer, "no")
        assert matched_ok == {ok_notice_id}
        assert matched_no == {no_notice_id}
    finally:
        _cleanup([ok_notice_id, no_notice_id])


def test_filter_notice_ids_by_eligibility_excludes_notices_without_analysis(temp_customer: int):
    with engine.begin() as conn:
        no_analysis_notice_id = _make_notice_with_eligibility(conn, axes=None)
        conn.execute(customer.update().where(customer.c.id == temp_customer).values(eligibility_company_size_tier="중소기업"))
    try:
        with engine.connect() as conn:
            matched = filter_notice_ids_by_eligibility(conn, [no_analysis_notice_id], temp_customer, "unknown")
        assert no_analysis_notice_id not in matched  # 미분석 공고는 후보군에서 아예 제외
    finally:
        _cleanup([no_analysis_notice_id])


def test_get_notice_eligibility_route_returns_verdict(client: TestClient, temp_customer: int):
    axes = dict(_ALL_NO_RESTRICTION, company_size_allowed_tiers=["중소기업"], company_size_cite="제2장 (1)")
    with engine.begin() as conn:
        notice_id = _make_notice_with_eligibility(conn, axes=axes)
        conn.execute(customer.update().where(customer.c.id == temp_customer).values(eligibility_company_size_tier="중소기업"))
    try:
        response = client.get(f"/api/notices/{notice_id}/eligibility", params={"customer_id": temp_customer})
        assert response.status_code == 200
        body = response.json()
        assert body["overall"] == "ok"
        assert body["axes"]["company_size"]["cite"] == "제2장 (1)"
    finally:
        _cleanup([notice_id])


def test_get_notice_eligibility_route_null_when_not_yet_analyzed(client: TestClient, temp_customer: int):
    with engine.begin() as conn:
        notice_id = _make_notice_with_eligibility(conn, axes=None)
    try:
        response = client.get(f"/api/notices/{notice_id}/eligibility", params={"customer_id": temp_customer})
        assert response.status_code == 200
        assert response.json() is None
    finally:
        _cleanup([notice_id])


def test_get_notice_eligibility_route_requires_auth():
    anon = TestClient(app)
    response = anon.get("/api/notices/1/eligibility", params={"customer_id": 1})
    assert response.status_code == 401


# ---- 공고 목록 자격요건 필터(2026-09-23, 5단계) ------------------------------------------


def test_list_notices_filters_by_eligibility_status(client: TestClient, temp_customer: int):
    ok_axes = _ALL_NO_RESTRICTION
    no_axes = dict(_ALL_NO_RESTRICTION, company_size_allowed_tiers=["대기업"], company_size_cite="제2장 (1)")
    with engine.begin() as conn:
        ok_notice_id = _make_notice_with_eligibility(conn, axes=ok_axes)
        no_notice_id = _make_notice_with_eligibility(conn, axes=no_axes)
        conn.execute(customer.update().where(customer.c.id == temp_customer).values(eligibility_company_size_tier="중소기업"))
    try:
        response_ok = client.get(
            "/api/notices",
            params={"tab": "all", "eligibility_customer_id": temp_customer, "eligibility_status": "ok"},
        )
        assert response_ok.status_code == 200
        ok_ids = {item["id"] for item in response_ok.json()["items"]}
        assert ok_notice_id in ok_ids
        assert no_notice_id not in ok_ids

        response_no = client.get(
            "/api/notices",
            params={"tab": "all", "eligibility_customer_id": temp_customer, "eligibility_status": "no"},
        )
        no_ids = {item["id"] for item in response_no.json()["items"]}
        assert no_notice_id in no_ids
        assert ok_notice_id not in no_ids
    finally:
        _cleanup([ok_notice_id, no_notice_id])


def test_list_notices_eligibility_filter_excludes_unanalyzed_notices(client: TestClient, temp_customer: int):
    """A2가 자격요건까지 구조화하지 않은 공고는 어떤 status를 물어봐도 후보군에서 아예
    빠져야 한다(하드 필터) — "확인 필요"를 물어봐도 이 공고 자체가 안 나온다."""
    with engine.begin() as conn:
        unanalyzed_notice_id = _make_notice_with_eligibility(conn, axes=None)
        conn.execute(customer.update().where(customer.c.id == temp_customer).values(eligibility_company_size_tier="중소기업"))
    try:
        response = client.get(
            "/api/notices",
            params={"tab": "all", "eligibility_customer_id": temp_customer, "eligibility_status": "unknown"},
        )
        ids = {item["id"] for item in response.json()["items"]}
        assert unanalyzed_notice_id not in ids
    finally:
        _cleanup([unanalyzed_notice_id])


def test_list_notices_eligibility_filter_reports_correct_total_and_pagination(client: TestClient, temp_customer: int):
    with engine.begin() as conn:
        notice_ids = [_make_notice_with_eligibility(conn, axes=_ALL_NO_RESTRICTION) for _ in range(3)]
        conn.execute(customer.update().where(customer.c.id == temp_customer).values(eligibility_company_size_tier="중소기업"))
    try:
        response = client.get(
            "/api/notices",
            params={
                "tab": "all", "eligibility_customer_id": temp_customer, "eligibility_status": "ok",
                "page": 1, "size": 2,
            },
        )
        body = response.json()
        assert body["total"] >= 3  # 공유 개발 DB에 다른 ok 판정 공고가 있을 수 있어 >=로 확인
        returned_ids = {item["id"] for item in body["items"]}
        assert returned_ids <= set(notice_ids) or len(body["items"]) == 2  # 페이지 크기 준수
        assert len(body["items"]) <= 2
    finally:
        _cleanup(notice_ids)


def test_list_notices_ignores_eligibility_status_without_customer(client: TestClient):
    """customer_id 없이 status만 주면 자격요건 필터 자체가 적용 안 돼야 한다(둘 다 있어야
    필터가 걸림 — NoticeFilters 계약)."""
    response = client.get("/api/notices", params={"tab": "all", "eligibility_status": "ok"})
    assert response.status_code == 200  # 422 등으로 거부하지 않고 그냥 무시
