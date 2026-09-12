"""관심주제 리포트 + 서명된 공유 링크(로그인 없음) 검증."""

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
from sqlalchemy import delete, func, select

from app.db import engine
from app.main import app
from app.models import newsletter_report, notice_strategy

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"


@pytest.fixture(autouse=True)
def _no_real_extraction():
    """리포트 생성이 이제 매칭된 공고마다 첨부문서 자동분석(A1)을 시도한다(2026-09-05) —
    테스트에서까지 실제 나라장터/IRIS로 나가면 느리고 외부망에 의존하게 되므로 막는다.
    추출 로직 자체는 test_analysis_pilot.py가 이미 따로 검증한다."""
    with mock.patch("app.services.interest_report.run_extraction_pilot") as m:
        yield m


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    response = c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    return c


@pytest.fixture
def grib_customer_id(client: TestClient) -> int:
    """실제 "(주)그립" 고객을 쓴다 — 별도 임시 고객을 만들지 않는 이유는 관심주제·리포트가
    고객 단위로 격리되는지를 검증하는 게 아니라 그립 자신의 실제 시드 데이터(관심주제·공고)로
    리포트 생성 로직 자체를 검증하기 때문. 단, 이 테스트들이 실제 계정에 리포트를 실제로
    쌓기 때문에(2026-09-05, "보고서 관리"에 테스트 리포트 수백 건이 쌓여있던 사고 발견)
    테스트가 만든 리포트는 반드시 정리한다."""
    customers = client.get("/api/customers").json()
    customer_id = next(c["id"] for c in customers if c["plan_tier"] == "internal")
    with engine.connect() as conn:
        max_id_before = conn.execute(
            select(func.max(newsletter_report.c.id)).where(newsletter_report.c.customer_id == customer_id)
        ).scalar()
        max_strategy_id_before = conn.execute(
            select(func.max(notice_strategy.c.id)).where(notice_strategy.c.customer_id == customer_id)
        ).scalar()
    yield customer_id
    with engine.begin() as conn:
        conn.execute(
            delete(newsletter_report).where(
                newsletter_report.c.customer_id == customer_id,
                newsletter_report.c.id > (max_id_before or 0),
            )
        )
        conn.execute(
            delete(notice_strategy).where(
                notice_strategy.c.customer_id == customer_id,
                notice_strategy.c.id > (max_strategy_id_before or 0),
            )
        )


def test_generate_report_creates_snapshot(client: TestClient, grib_customer_id: int):
    response = client.post(f"/api/customers/{grib_customer_id}/reports")
    assert response.status_code == 201
    body = response.json()
    assert body["token"]
    assert body["customer_id"] == grib_customer_id
    assert "notices" in body and "summary" in body
    assert body["summary"]["total"] == len(body["notices"])


def test_generate_report_summary_includes_attributions_list(client: TestClient, grib_customer_id: int):
    # advisory INBOX #7(2026-09-01) — 출처표시 문구는 사람이 붙이는 게 아니라 생성 시점에
    # source.attribution_text에서 자동으로 모여야 한다(내용 자체는 시드 소스 배정에 따라
    # 달라질 수 있어 타입/키 존재만 검증).
    response = client.post(f"/api/customers/{grib_customer_id}/reports")
    body = response.json()
    assert isinstance(body["summary"]["attributions"], list)
    assert all(isinstance(a, str) for a in body["summary"]["attributions"])


def test_generate_report_404_for_unknown_customer(client: TestClient):
    response = client.post("/api/customers/999999/reports")
    assert response.status_code == 404


def test_list_reports_returns_generated(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    listed = client.get(f"/api/customers/{grib_customer_id}/reports").json()
    assert any(r["token"] == created["token"] for r in listed)


def test_public_report_requires_no_auth(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()

    anon = TestClient(app)  # 로그인 안 함
    response = anon.get(f"/api/public/reports/{created['token']}")
    assert response.status_code == 200
    body = response.json()
    assert body["customer_name"]
    assert body["notices"] == created["notices"]


def test_public_report_unknown_token_404():
    anon = TestClient(app)
    response = anon.get("/api/public/reports/does-not-exist")
    assert response.status_code == 404


def test_public_report_view_count_increments(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    token = created["token"]
    anon = TestClient(app)

    first = anon.get(f"/api/public/reports/{token}").json()
    second = anon.get(f"/api/public/reports/{token}").json()
    assert second["view_count"] == first["view_count"] + 1


def test_report_snapshot_is_frozen_after_profile_change(client: TestClient, grib_customer_id: int):
    # 그립 자신의 실제 관심주제 프로필을 건드리므로(2026-09-05 발견 — 이 테스트가 실제 프로필을
    # 빈 상태로 남겨두고 있었음) 시작 전 상태를 저장해뒀다가 끝나면 복원한다.
    original = client.get(f"/api/customers/{grib_customer_id}/interests").json()

    topics = original["topics"]
    client.put(
        f"/api/customers/{grib_customer_id}/interests",
        json={"topic_ids": [topics[0]["id"]], "terms": [], "followed_org_ids": []},
    )
    created = client.post(f"/api/customers/{grib_customer_id}/reports")
    snapshot = created.json()["notices"]

    # 프로필을 완전히 바꿔도(빈 프로필로) 이미 생성된 리포트 스냅샷은 그대로여야 함.
    client.put(
        f"/api/customers/{grib_customer_id}/interests",
        json={"topic_ids": [], "terms": [], "followed_org_ids": []},
    )
    anon = TestClient(app)
    fetched = anon.get(f"/api/public/reports/{created.json()['token']}").json()
    assert fetched["notices"] == snapshot

    client.put(
        f"/api/customers/{grib_customer_id}/interests",
        json={"topic_ids": original["topic_ids"], "terms": original["terms"], "followed_org_ids": original["followed_org_ids"]},
    )


# ---- 공개 공고 상세·AI 사업 추진 전략(2026-09-05) ----------------------------------


def test_public_notice_detail_requires_valid_token_and_membership(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    token = created["token"]
    notices = created["notices"]

    anon = TestClient(app)
    if notices:
        notice_id = notices[0]["id"]
        response = anon.get(f"/api/public/reports/{token}/notices/{notice_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == notice_id
        assert "notice_status_label" in body

    # 이 리포트에 없는(존재하지 않는) 공고 id는 404 — 토큰으로 임의 공고를 못 보게 막는다.
    response = anon.get(f"/api/public/reports/{token}/notices/999999999")
    assert response.status_code == 404

    # 토큰 자체가 없으면 404.
    response = anon.get("/api/public/reports/does-not-exist/notices/1")
    assert response.status_code == 404


# ---- 공고탐색과 같은 상세 분석(A2 탭·A1 첨부원문)을 리포트에도 노출(2026-09-12) -------------


def test_public_notice_requirements_matches_admin_route_shape(client: TestClient, grib_customer_id: int):
    """공개 라우트가 관리자용(get_requirements)과 같은 서비스 함수를 그대로 쓰므로, 응답
    모양(analysis_id·status·step·summary·requirements 키)이 같아야 한다."""
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    token = created["token"]
    notices = created["notices"]
    if not notices:
        pytest.skip("그립 고객에 매칭된 공고가 없어 이 테스트를 건너뜀")
    notice_id = notices[0]["id"]

    admin_result = client.get(f"/api/notices/{notice_id}/requirements").json()
    anon = TestClient(app)
    public_result = anon.get(f"/api/public/reports/{token}/notices/{notice_id}/requirements").json()
    assert public_result == admin_result


def test_public_notice_requirements_404_for_notice_not_in_report(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    anon = TestClient(app)
    response = anon.get(f"/api/public/reports/{created['token']}/notices/999999999/requirements")
    assert response.status_code == 404


def test_public_notice_extraction_matches_admin_route_shape(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    token = created["token"]
    notices = created["notices"]
    if not notices:
        pytest.skip("그립 고객에 매칭된 공고가 없어 이 테스트를 건너뜀")
    notice_id = notices[0]["id"]

    admin_result = client.get(f"/api/notices/{notice_id}/extract").json()
    anon = TestClient(app)
    public_result = anon.get(f"/api/public/reports/{token}/notices/{notice_id}/extract").json()
    assert public_result == admin_result


def test_public_notice_extraction_404_for_notice_not_in_report(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    anon = TestClient(app)
    response = anon.get(f"/api/public/reports/{created['token']}/notices/999999999/extract")
    assert response.status_code == 404


def test_public_notice_strategy_generation_is_idempotent(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    notices = created["notices"]
    if not notices:
        pytest.skip("그립 고객에 매칭된 공고가 없어 이 테스트를 건너뜀")
    token = created["token"]
    notice_id = notices[0]["id"]

    anon = TestClient(app)
    summary_md = "## 공고 핵심 요약\n- 테스트 전략\n"
    with mock.patch(
        "app.services.notice_strategy.fetch",
        return_value=mock.Mock(json=lambda: {"content": [{"type": "text", "text": summary_md}], "usage": {"input_tokens": 100, "output_tokens": 50}}),
    ) as mock_fetch, mock.patch("app.config.settings.anthropic_api_key", "sk-ant-test"):
        first = anon.post(f"/api/public/reports/{token}/notices/{notice_id}/strategy")
        assert first.status_code == 200
        assert first.json()["status"] == "done"
        assert first.json()["strategy_md"] == summary_md

        second = anon.post(f"/api/public/reports/{token}/notices/{notice_id}/strategy")
        assert second.json() == first.json()
        assert mock_fetch.call_count == 1  # 여러 번 눌러도 LLM 호출은 한 번뿐

    # 2026-09-12 — 이미 생성된 전략은 공고 상세 조회(get_public_notice)에도 그대로 보여야
    # 프론트가 "생성" 버튼을 다시 안 띄우고 바로 내용을 보여줄 수 있다.
    notice_detail = anon.get(f"/api/public/reports/{token}/notices/{notice_id}").json()
    assert notice_detail["strategy"] == {"status": "done", "strategy_md": summary_md}


def test_public_notice_detail_has_no_strategy_before_generation(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    notices = created["notices"]
    if not notices:
        pytest.skip("그립 고객에 매칭된 공고가 없어 이 테스트를 건너뜀")
    notice_id = notices[0]["id"]

    anon = TestClient(app)
    notice_detail = anon.get(f"/api/public/reports/{created['token']}/notices/{notice_id}").json()
    assert notice_detail["strategy"] is None


def test_public_notice_strategy_404_for_notice_not_in_report(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    anon = TestClient(app)
    response = anon.post(f"/api/public/reports/{created['token']}/notices/999999999/strategy")
    assert response.status_code == 404


# ---- 리포트 생성 시 A1 재추출 스킵(2026-09-07) -------------------------------------
#
# 실측 발견 — 리포트 생성이 매번 상위 20건 전부를 무조건 다시 추출 시도해서, 이미 한 번
# 시도한(성공이든 0건이든) 공고까지 매번 재추출하고 있었다. 나라장터(용역) 소스가 그날
# apis.data.go.kr 지연으로 느려지자 "지금 생성"이 몇 분씩 걸리는 원인이 됐다(그립 실제
# 리포트 상위 20건 중 16건이 그 소스였음). pending_analysis.py의 자동 패스와 같은 규칙
# (이미 시도한 공고는 건너뜀)으로 맞췄다.


@pytest.fixture
def notice_without_analysis():
    from sqlalchemy import insert

    from app.models import notice, source

    with engine.connect() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
    with engine.begin() as conn:
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] A1 미시도 공고",
                url="https://example.grib-test.kr/notice/no-analysis-yet",
            ).returning(notice.c.id)
        ).scalar_one()
    yield notice_id
    with engine.begin() as conn:
        conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_ensure_notices_extracted_skips_already_attempted(notice_without_analysis):
    from sqlalchemy import insert

    from app.models import analysis
    from app.services.interest_report import _ensure_notices_extracted

    with engine.begin() as conn:
        already_attempted_id = conn.execute(
            insert(analysis)
            .values(
                notice_id=notice_without_analysis, step="A1_extract", status="failed", source_kind="notice",
                input_ref="https://example.grib-test.kr/notice/no-analysis-yet",
            )
            .returning(analysis.c.id)
        ).scalar_one()
    try:
        with mock.patch("app.services.interest_report.run_extraction_pilot") as mock_run:
            _ensure_notices_extracted([notice_without_analysis])
        mock_run.assert_not_called()
    finally:
        with engine.begin() as conn:
            conn.execute(delete(analysis).where(analysis.c.id == already_attempted_id))


def test_ensure_notices_extracted_runs_for_never_attempted(notice_without_analysis):
    from app.services.interest_report import _ensure_notices_extracted

    with mock.patch("app.services.interest_report.run_extraction_pilot") as mock_run:
        _ensure_notices_extracted([notice_without_analysis])
    mock_run.assert_called_once()


# ---- 보고서 삭제(수동·자동 보관기간)·발송(2026-09-12) --------------------------------


def test_delete_report_removes_it(client: TestClient, grib_customer_id: int):
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    response = client.delete(f"/api/customers/{grib_customer_id}/reports/{created['id']}")
    assert response.status_code == 204

    listed = client.get(f"/api/customers/{grib_customer_id}/reports").json()
    assert all(r["id"] != created["id"] for r in listed)


def test_delete_report_404_for_unknown_report(client: TestClient, grib_customer_id: int):
    response = client.delete(f"/api/customers/{grib_customer_id}/reports/999999999")
    assert response.status_code == 404


def test_delete_report_404_when_customer_mismatched(client: TestClient, grib_customer_id: int):
    """다른 고객 소유 보고서를 자기 고객 id로 지우려 하면 거부돼야 한다(권한 우회 방지)."""
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    response = client.delete(f"/api/customers/999999999/reports/{created['id']}")
    assert response.status_code == 404


def test_send_report_calls_mailer_with_recipients_and_link(client: TestClient, grib_customer_id: int):
    from app.models import customer

    with engine.begin() as conn:
        conn.execute(
            customer.update().where(customer.c.id == grib_customer_id).values(report_recipient_emails=["a@example.com"])
        )
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()

    with mock.patch("app.services.mailer.smtplib.SMTP_SSL") as mock_smtp, mock.patch(
        "app.config.settings.smtp_host", "smtp.example.com"
    ), mock.patch("app.config.settings.smtp_user", "u"), mock.patch("app.config.settings.smtp_password", "p"):
        response = client.post(f"/api/customers/{grib_customer_id}/reports/{created['id']}/send")

    assert response.status_code == 200
    assert response.json()["sent_to"] == ["a@example.com"]
    mock_smtp.return_value.__enter__.return_value.send_message.assert_called_once()


def test_send_report_email_body_includes_notice_list(client: TestClient, grib_customer_id: int):
    """2026-09-12 사용자 지시 — "메일 본문에 관심공고 페이지를 바로 보여줄 수 있도록" —
    링크 하나뿐이던 이메일 본문에 공고 목록(제목·발주기관·사업비·마감일)이 직접 들어가야 한다."""
    from app.models import customer

    with engine.begin() as conn:
        conn.execute(
            customer.update().where(customer.c.id == grib_customer_id).values(report_recipient_emails=["a@example.com"])
        )
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()
    notices = created["notices"]
    if not notices:
        pytest.skip("그립 고객에 매칭된 공고가 없어 이 테스트를 건너뜀")

    with mock.patch("app.services.mailer.smtplib.SMTP_SSL") as mock_smtp, mock.patch(
        "app.config.settings.smtp_host", "smtp.example.com"
    ), mock.patch("app.config.settings.smtp_user", "u"), mock.patch("app.config.settings.smtp_password", "p"):
        response = client.post(f"/api/customers/{grib_customer_id}/reports/{created['id']}/send")
    assert response.status_code == 200

    sent_msg = mock_smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
    html_part = next(part for part in sent_msg.iter_parts() if part.get_content_type() == "text/html")
    html_body = html_part.get_content()
    for n in notices[:5]:  # 전부 확인하면 느리고, 목록 로직 자체는 위에서 이미 검증됨
        assert n["title"] in html_body
        assert f"/r/{created['token']}/notices/{n['id']}" in html_body


def test_send_report_422_without_recipients(client: TestClient, grib_customer_id: int):
    from app.models import customer

    with engine.begin() as conn:
        conn.execute(customer.update().where(customer.c.id == grib_customer_id).values(report_recipient_emails=[]))
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()

    with mock.patch("app.config.settings.smtp_host", "smtp.example.com"), mock.patch(
        "app.config.settings.smtp_user", "u"
    ), mock.patch("app.config.settings.smtp_password", "p"):
        response = client.post(f"/api/customers/{grib_customer_id}/reports/{created['id']}/send")
    assert response.status_code == 422


def test_send_report_501_when_smtp_not_configured(client: TestClient, grib_customer_id: int):
    from app.models import customer

    with engine.begin() as conn:
        conn.execute(
            customer.update().where(customer.c.id == grib_customer_id).values(report_recipient_emails=["a@example.com"])
        )
    created = client.post(f"/api/customers/{grib_customer_id}/reports").json()

    with mock.patch("app.config.settings.smtp_host", ""):
        response = client.post(f"/api/customers/{grib_customer_id}/reports/{created['id']}/send")
    assert response.status_code == 501


def test_send_report_404_for_unknown_report(client: TestClient, grib_customer_id: int):
    response = client.post(f"/api/customers/{grib_customer_id}/reports/999999999/send")
    assert response.status_code == 404


def test_delete_expired_reports_removes_only_old_ones(grib_customer_id: int):
    from datetime import datetime, timedelta, timezone

    from app.models import newsletter_report
    from app.services.app_settings import set_report_retention_days
    from app.services.interest_report import delete_expired_reports

    with engine.begin() as conn:
        old_id = conn.execute(
            newsletter_report.insert()
            .values(customer_id=grib_customer_id, token="test-old-token", notices=[], summary={})
            .returning(newsletter_report.c.id)
        ).scalar_one()
        conn.execute(
            newsletter_report.update()
            .where(newsletter_report.c.id == old_id)
            .values(generated_at=datetime.now(timezone.utc) - timedelta(days=100))
        )
        recent_id = conn.execute(
            newsletter_report.insert()
            .values(customer_id=grib_customer_id, token="test-recent-token", notices=[], summary={})
            .returning(newsletter_report.c.id)
        ).scalar_one()
        set_report_retention_days(conn, 90)

    try:
        with engine.begin() as conn:
            deleted = delete_expired_reports(conn)
        assert deleted >= 1

        with engine.connect() as conn:
            remaining_ids = set(
                conn.execute(select(newsletter_report.c.id).where(newsletter_report.c.customer_id == grib_customer_id)).scalars()
            )
        assert old_id not in remaining_ids
        assert recent_id in remaining_ids
    finally:
        with engine.begin() as conn:
            conn.execute(delete(newsletter_report).where(newsletter_report.c.id.in_([old_id, recent_id])))
            set_report_retention_days(conn, None)


def test_delete_expired_reports_noop_when_retention_not_set(grib_customer_id: int):
    from app.models import newsletter_report
    from app.services.app_settings import set_report_retention_days
    from app.services.interest_report import delete_expired_reports

    with engine.begin() as conn:
        set_report_retention_days(conn, None)
        old_id = conn.execute(
            newsletter_report.insert()
            .values(customer_id=grib_customer_id, token="test-noop-token", notices=[], summary={})
            .returning(newsletter_report.c.id)
        ).scalar_one()

    try:
        with engine.begin() as conn:
            assert delete_expired_reports(conn) == 0
        with engine.connect() as conn:
            assert conn.execute(select(newsletter_report.c.id).where(newsletter_report.c.id == old_id)).first() is not None
    finally:
        with engine.begin() as conn:
            conn.execute(delete(newsletter_report).where(newsletter_report.c.id == old_id))
