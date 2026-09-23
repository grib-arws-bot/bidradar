"""관심주제 키워드(keyword_rule) 관리자 CRUD + rescan 검증(2026-09-05 요청)."""

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
from sqlalchemy import delete, func, insert, select

from app.db import engine
from app.main import app
from app.models import audit_log, interest_topic, keyword_rule, notice, notice_score, source

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"


@pytest.fixture(autouse=True)
def _cleanup_keyword_audit_log():
    """이 파일의 테스트가 남기는 audit_log(keyword.create/update/delete/rescan)를 정리한다 —
    감사로그는 target_id가 없는 rescan 액션도 있어 topic_id로 걸러낼 수 없다. 테스트 시작
    전 최대 id를 기록해뒀다가 그 이후 생긴 keyword.* 로그만 지운다(2026-09-05, 실제 사용자
    keyword.delete 로그가 테스트 잔재 18건에 섞여 있던 걸 발견해 추가)."""
    with engine.connect() as conn:
        watermark = conn.execute(select(func.max(audit_log.c.id))).scalar() or 0
    yield
    with engine.begin() as conn:
        conn.execute(delete(audit_log).where(audit_log.c.id > watermark, audit_log.c.action.like("keyword.%")))


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    return c


def _any_source_id(conn) -> int:
    return conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()


@pytest.fixture
def temp_topic():
    with engine.begin() as conn:
        topic_id = conn.execute(
            insert(interest_topic).values(name="[테스트] 키워드검증용 분류", sort_order=999).returning(interest_topic.c.id)
        ).scalar_one()
    yield topic_id
    with engine.begin() as conn:
        conn.execute(delete(keyword_rule).where(keyword_rule.c.interest_topic_id == topic_id))
        conn.execute(delete(notice_score).where(notice_score.c.interest_topic_id == topic_id))
        conn.execute(delete(interest_topic).where(interest_topic.c.id == topic_id))


def test_keywords_requires_auth():
    assert TestClient(app).get("/api/admin/topics/1/keywords").status_code == 401


def test_create_list_update_delete_keyword(client: TestClient, temp_topic: int):
    created = client.post(f"/api/admin/topics/{temp_topic}/keywords", json={"term": "__테스트키워드", "weight_class": "tech", "weight": 2})
    assert created.status_code == 201
    keyword_id = created.json()["id"]
    assert created.json()["term"] == "__테스트키워드"

    listed = client.get(f"/api/admin/topics/{temp_topic}/keywords").json()
    assert any(k["id"] == keyword_id for k in listed)

    updated = client.patch(f"/api/admin/topics/keywords/{keyword_id}", json={"weight": 3, "active": False})
    assert updated.status_code == 200
    assert updated.json()["weight"] == 3
    assert updated.json()["active"] is False

    deleted = client.delete(f"/api/admin/topics/keywords/{keyword_id}")
    assert deleted.status_code == 204

    listed_after = client.get(f"/api/admin/topics/{temp_topic}/keywords").json()
    assert not any(k["id"] == keyword_id for k in listed_after)


def test_create_keyword_rejects_bad_weight_class(client: TestClient, temp_topic: int):
    response = client.post(f"/api/admin/topics/{temp_topic}/keywords", json={"term": "x", "weight_class": "unknown", "weight": 1})
    assert response.status_code == 400


def test_create_keyword_rejects_unknown_topic(client: TestClient):
    response = client.post("/api/admin/topics/999999999/keywords", json={"term": "x", "weight_class": "tech", "weight": 2})
    assert response.status_code == 400


def test_update_keyword_404_for_unknown_id(client: TestClient):
    response = client.patch("/api/admin/topics/keywords/999999999", json={"weight": 5})
    assert response.status_code == 404


def test_delete_keyword_404_for_unknown_id(client: TestClient):
    response = client.delete("/api/admin/topics/keywords/999999999")
    assert response.status_code == 404


# ---- rescan ------------------------------------------------------------------------


@pytest.fixture
def temp_notice_with_keyword_title():
    with engine.begin() as conn:
        notice_id = conn.execute(
            insert(notice).values(
                source_id=_any_source_id(conn), source_ver=1, stage="입찰공고",
                title="[테스트] __재스캔키워드매치 공고", url="https://example.grib-test.kr/notice/rescan-test",
            ).returning(notice.c.id)
        ).scalar_one()
    yield notice_id
    with engine.begin() as conn:
        conn.execute(delete(notice_score).where(notice_score.c.notice_id == notice_id))
        conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_rescan_adds_new_match_without_touching_existing(
    client: TestClient, temp_topic: int, temp_notice_with_keyword_title: int
):
    # 재스캔 전에는 매칭 없음(새 키워드가 아직 없으므로)
    before = client.get(f"/api/admin/topics/{temp_topic}/keywords").json()
    assert before == []

    # 다른 관심주제에 이미 있는(재스캔이 절대 건드리면 안 되는) 기존 매칭 하나를 심어둔다.
    with engine.connect() as conn:
        other_topic_id = conn.execute(select(interest_topic.c.id).where(interest_topic.c.id != temp_topic).limit(1)).scalar_one()
    with engine.begin() as conn:
        conn.execute(
            insert(notice_score).values(
                notice_id=temp_notice_with_keyword_title, interest_topic_id=other_topic_id,
                l2_score=99, reason="사전 존재(재스캔이 건드리면 안 됨)", rule_ver=0,
            )
        )

    client.post(f"/api/admin/topics/{temp_topic}/keywords", json={"term": "__재스캔키워드매치", "weight_class": "core", "weight": 4})

    result = client.post("/api/admin/topics/keywords/rescan")
    assert result.status_code == 200
    assert result.json()["added"] >= 1

    with engine.connect() as conn:
        rows = conn.execute(
            select(notice_score.c.interest_topic_id, notice_score.c.reason).where(
                notice_score.c.notice_id == temp_notice_with_keyword_title
            )
        ).all()
    topic_ids = {r[0] for r in rows}
    assert temp_topic in topic_ids  # 새로 추가됨
    assert other_topic_id in topic_ids  # 기존 것도 그대로 남아있음(안 건드림)

    # 다시 실행해도 중복 추가되지 않는다.
    result2 = client.post("/api/admin/topics/keywords/rescan")
    with engine.connect() as conn:
        count = conn.execute(
            select(notice_score.c.id).where(
                notice_score.c.notice_id == temp_notice_with_keyword_title, notice_score.c.interest_topic_id == temp_topic
            )
        ).all()
    assert len(count) == 1
