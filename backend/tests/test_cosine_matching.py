"""app/services/cosine_matching.py 검증(2026-09-16) — 규칙 매칭과 나란히 비교하는 신호라
같은 후보 풀·하드 필터를 그대로 쓰는지, 아직 임베딩 없는 공고를 제외하는지 확인한다.
임베딩 모델 호출은 항상 mock — 이 테스트에서 실제로 무거운 모델을 로딩하지 않는다.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest import mock

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
from app.models import customer, interest_topic, notice, notice_score, source
from app.services.cosine_matching import top_matches_cosine
from app.services.customer_interest import InterestDraft, get_interest_profile

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"

# 코사인 거리 0(완전 동일)·2(완전 반대) 근사값 — Vector.cosine_distance()를 실제로 계산하는
# pgvector 확장이 반환하는 값이므로 여기선 "가까운 벡터"·"먼 벡터"를 방향으로만 구분한다.
CLOSE_VECTOR = [1.0] + [0.0] * 1023
FAR_VECTOR = [-1.0] + [0.0] * 1023
QUERY_VECTOR = [1.0] + [0.0] * 1023


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    response = c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    return c


def _make_notice(
    conn, source_id: int, *, embedding=None, embedding_a1=None, close_dt=None, title="[테스트] 코사인 매칭"
) -> int:
    return conn.execute(
        insert(notice).values(
            source_id=source_id, source_ver=1, stage="입찰공고", title=title,
            url=f"https://example.grib-test.kr/notice/cosine-{id(object())}",
            embedding=embedding, embedding_a1=embedding_a1, close_dt=close_dt,
        ).returning(notice.c.id)
    ).scalar_one()


def _cleanup(notice_ids: list[int]) -> None:
    with engine.begin() as conn:
        conn.execute(delete(notice_score).where(notice_score.c.notice_id.in_(notice_ids)))
        conn.execute(delete(notice).where(notice.c.id.in_(notice_ids)))


def _draft() -> InterestDraft:
    with engine.connect() as conn:
        topic_id = conn.execute(select(interest_topic.c.id).limit(1)).scalar_one()
    return InterestDraft(topic_ids=[topic_id])


def _profile() -> dict:
    # customer_id는 top_matches_cosine이 AI 프로필 요약(profile_summary_md)을 조회할 때 쓴다
    # (2026-09-17) — get_interest_profile()이 실제로 채워주는 필드라 여기서도 실제 고객 하나를
    # 가리키게 한다(시드 데이터의 "그립" 내부 고객 등 항상 최소 1건 존재).
    with engine.connect() as conn:
        customer_id = conn.execute(select(customer.c.id).limit(1)).scalar_one()
    return {
        "customer_id": customer_id,
        "topics": [{"id": 1, "name": "테스트주제"}],
        "topic_ids": [1],
        "topic_priorities": {},
        "terms": [],
    }


def test_excludes_notices_without_embedding():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        with_embedding_id = _make_notice(conn, source_id, embedding=CLOSE_VECTOR)
        without_embedding_id = _make_notice(conn, source_id, embedding=None)
    try:
        with mock.patch("app.services.cosine_matching.embed_texts", return_value=[QUERY_VECTOR]):
            with engine.connect() as conn:
                result = top_matches_cosine(conn, _draft(), _profile(), limit=20)
        matched_ids = {m["id"] for m in result["matches"]}
        assert with_embedding_id in matched_ids
        assert without_embedding_id not in matched_ids
        assert result["pending_embeddings"] >= 1
    finally:
        _cleanup([with_embedding_id, without_embedding_id])


def test_applies_same_hard_filters_as_rule_matching():
    """마감된 공고는 임베딩이 있어도 규칙 매칭과 똑같이 제외돼야 한다(_passes_hard_filters
    재사용 검증) — 두 방식이 서로 다른 후보 풀을 쓰면 비교 자체가 무의미해진다."""
    past = datetime.now(timezone.utc) - timedelta(days=1)
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        closed_id = _make_notice(conn, source_id, embedding=CLOSE_VECTOR, close_dt=past)
    try:
        with mock.patch("app.services.cosine_matching.embed_texts", return_value=[QUERY_VECTOR]):
            with engine.connect() as conn:
                result = top_matches_cosine(conn, _draft(), _profile(), limit=20)
        assert closed_id not in {m["id"] for m in result["matches"]}
    finally:
        _cleanup([closed_id])


def test_orders_by_similarity_closest_first():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        close_id = _make_notice(conn, source_id, embedding=CLOSE_VECTOR, title="[테스트] 가까운 벡터")
        far_id = _make_notice(conn, source_id, embedding=FAR_VECTOR, title="[테스트] 먼 벡터")
    try:
        with mock.patch("app.services.cosine_matching.embed_texts", return_value=[QUERY_VECTOR]):
            with engine.connect() as conn:
                # 공유 개발 DB에 이미 임베딩된 실제 공고가 많을 수 있어(146번 항목과 같은 클래스
                # 문제 — 이번 세션에 실제 검증용으로 40건을 채워둠) limit=20이면 우리 테스트
                # 공고 중 하나가 상위 밖으로 밀려날 수 있다. 두 건 다 반드시 포함되도록 충분히
                # 큰 limit을 준다 — 이 테스트의 관심사는 "몇 등인지"가 아니라 "상대 순서"다.
                result = top_matches_cosine(conn, _draft(), _profile(), limit=50_000)
        ids_in_order = [m["id"] for m in result["matches"]]
        assert ids_in_order.index(close_id) < ids_in_order.index(far_id)
        close_match = next(m for m in result["matches"] if m["id"] == close_id)
        far_match = next(m for m in result["matches"] if m["id"] == far_id)
        assert close_match["cosine_score"] > far_match["cosine_score"]
    finally:
        _cleanup([close_id, far_id])


def test_top_matches_cosine_attachment_variant_uses_embedding_a1_column():
    """variant="attachment"는 embedding이 아니라 embedding_a1을 봐야 한다 — 반대로 채워진
    공고(embedding만 있고 embedding_a1은 없음)는 이 variant에서 제외돼야 한다."""
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        with_a1_id = _make_notice(conn, source_id, embedding_a1=CLOSE_VECTOR)
        title_only_id = _make_notice(conn, source_id, embedding=CLOSE_VECTOR)
    try:
        with mock.patch("app.services.cosine_matching.embed_texts", return_value=[QUERY_VECTOR]):
            with engine.connect() as conn:
                result = top_matches_cosine(conn, _draft(), _profile(), limit=20, variant="attachment")
        matched_ids = {m["id"] for m in result["matches"]}
        assert with_a1_id in matched_ids
        assert title_only_id not in matched_ids
    finally:
        _cleanup([with_a1_id, title_only_id])


def test_compare_endpoint_returns_three_way_result_shapes(client: TestClient):
    """API 계층 배선 확인 — 규칙 매칭·코사인(제목)·코사인(첨부) 3방향 결과를 한 응답에 같이
    담아 돌려주는지만 본다(각 알고리즘의 세부 동작은 위 서비스 계층 테스트가 이미 검증)."""
    customer_id = client.post("/api/customers", json={"name": "[테스트] 비교 페이지", "plan_tier": "standard"}).json()["id"]
    try:
        with mock.patch("app.services.cosine_matching.embed_texts", return_value=[QUERY_VECTOR]):
            response = client.get(f"/api/customers/{customer_id}/interest-matches/compare")
        assert response.status_code == 200
        body = response.json()
        assert {
            "rule_based", "cosine", "pending_embeddings", "cosine_attachment", "pending_embeddings_attachment",
        } <= body.keys()
    finally:
        with engine.begin() as conn:
            from app.models import customer
            conn.execute(delete(customer).where(customer.c.id == customer_id))
