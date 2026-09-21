"""U5b 완료조건 검증: 저장 후 실제 건수 계산 · 수집 파이프라인 무영향 · 고객 간 격리.

2026-09-05 — 이전에는 시드 데이터의 "예시고객 A/B"에 기대어 테스트했으나, 사용자 지시로
그 가짜 예시 고객을 완전히 제거하면서(seed_data.py) 이 테스트들도 자체 임시 고객을
만들어 쓰도록 바꿨다(test_customer_management.py와 같은 패턴) — 시드 데이터 유무와 무관하게
항상 통과해야 한다.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

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
from app.models import customer, notice, notice_score, raw_payload, source, source_run
from app.services.customer_interest import (
    SECTION_LIMITS,
    TOPIC_STRENGTH_FLOOR,
    TOPIC_STRENGTH_REFERENCE,
    InterestDraft,
    _score_all,
    _section_of,
    _strength_label,
    _topic_strength,
    top_matches,
)

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    response = c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    return c


def _create_customer(client: TestClient, name: str) -> int:
    response = client.post("/api/customers", json={"name": name, "plan_tier": "standard"})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def customer_a_id(client: TestClient):
    customer_id = _create_customer(client, "[테스트] 관심주제 검증용 A")
    yield customer_id
    with engine.begin() as conn:
        conn.execute(customer.delete().where(customer.c.id == customer_id))


@pytest.fixture
def customer_b_id(client: TestClient):
    # "고객 B"는 관심 프로필을 아무것도 설정하지 않은 채로 둔다(빈 상태 확인용 — 11절).
    customer_id = _create_customer(client, "[테스트] 관심주제 검증용 B")
    yield customer_id
    with engine.begin() as conn:
        conn.execute(customer.delete().where(customer.c.id == customer_id))


def _table_counts(conn) -> dict[str, int]:
    return {
        "notice": conn.execute(select(func.count()).select_from(notice)).scalar_one(),
        "source": conn.execute(select(func.count()).select_from(source)).scalar_one(),
        "source_run": conn.execute(select(func.count()).select_from(source_run)).scalar_one(),
        "raw_payload": conn.execute(select(func.count()).select_from(raw_payload)).scalar_one(),
    }


def test_list_customers_includes_grib(client: TestClient):
    customers = client.get("/api/customers").json()
    assert any(c["plan_tier"] == "internal" for c in customers)


def test_get_interests_shape(client: TestClient, customer_a_id: int):
    response = client.get(f"/api/customers/{customer_a_id}/interests")
    assert response.status_code == 200
    body = response.json()
    assert {"topic_ids", "topic_priorities", "terms", "followed_org_ids", "price_min", "topics"} <= body.keys()
    assert len(body["topics"]) > 0
    assert body["price_min"] is None


def test_get_interests_404_for_unknown_customer(client: TestClient):
    response = client.get("/api/customers/999999/interests")
    assert response.status_code == 404


def test_save_does_not_touch_collection_pipeline(client: TestClient, customer_a_id: int):
    with engine.connect() as conn:
        before = _table_counts(conn)

    topics = client.get(f"/api/customers/{customer_a_id}/interests").json()["topics"]
    response = client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={"topic_ids": [topics[0]["id"], topics[1]["id"]], "terms": ["CCTV"], "followed_org_ids": []},
    )
    assert response.status_code == 204

    with engine.connect() as conn:
        after = _table_counts(conn)

    assert before == after


def test_customer_isolation(client: TestClient, customer_a_id: int, customer_b_id: int):
    topics = client.get(f"/api/customers/{customer_a_id}/interests").json()["topics"]

    b_before = client.get(f"/api/customers/{customer_b_id}/interests").json()

    response = client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={"topic_ids": [t["id"] for t in topics], "terms": ["영상관제"], "followed_org_ids": []},
    )
    assert response.status_code == 204

    b_after = client.get(f"/api/customers/{customer_b_id}/interests").json()
    assert b_before == b_after


# ---- 관심주제 3단계 우선순위(2026-09-05, "산업안전처럼 핵심 사업 주제는 더 높은 순위여야") ---


def test_save_and_load_topic_priority(client: TestClient, customer_a_id: int):
    topics = client.get(f"/api/customers/{customer_a_id}/interests").json()["topics"]
    topic_id = topics[0]["id"]
    response = client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={"topic_ids": [topic_id], "topic_priorities": {topic_id: "high"}, "terms": [], "followed_org_ids": []},
    )
    assert response.status_code == 204

    profile = client.get(f"/api/customers/{customer_a_id}/interests").json()
    assert profile["topic_priorities"] == {str(topic_id): "high"}


def test_save_omits_normal_priority_from_response(client: TestClient, customer_a_id: int):
    """normal은 굳이 응답에 채워 보내지 않는다(기본값이라 명시할 필요가 없음) — 우선순위를
    한 번도 안 정한 고객은 이전과 똑같은 빈 dict를 본다."""
    topics = client.get(f"/api/customers/{customer_a_id}/interests").json()["topics"]
    topic_id = topics[0]["id"]
    client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={"topic_ids": [topic_id], "terms": [], "followed_org_ids": []},
    )
    profile = client.get(f"/api/customers/{customer_a_id}/interests").json()
    assert profile["topic_priorities"] == {}


def test_save_rejects_invalid_priority(client: TestClient, customer_a_id: int):
    topics = client.get(f"/api/customers/{customer_a_id}/interests").json()["topics"]
    topic_id = topics[0]["id"]
    response = client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={"topic_ids": [topic_id], "topic_priorities": {topic_id: "urgent"}, "terms": [], "followed_org_ids": []},
    )
    assert response.status_code == 400


def test_save_and_load_price_min(client: TestClient, customer_a_id: int):
    response = client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={"topic_ids": [], "terms": [], "followed_org_ids": [], "price_min": 50_000_000},
    )
    assert response.status_code == 204
    profile = client.get(f"/api/customers/{customer_a_id}/interests").json()
    assert profile["price_min"] == 50_000_000

    # 다시 비우면(null) 필터가 없어져야 한다.
    client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={"topic_ids": [], "terms": [], "followed_org_ids": [], "price_min": None},
    )
    profile = client.get(f"/api/customers/{customer_a_id}/interests").json()
    assert profile["price_min"] is None


def test_save_rejects_negative_price_min(client: TestClient, customer_a_id: int):
    response = client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={"topic_ids": [], "terms": [], "followed_org_ids": [], "price_min": -1},
    )
    assert response.status_code == 400


def test_save_and_load_work_type_prefs(client: TestClient, customer_a_id: int):
    # 2026-09-21 — 관심 사업유형 선호(의사결정_로그 192번, 같은 날 +/중립/- 3단계로 확장)
    # 저장·조회 왕복 확인.
    response = client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={
            "topic_ids": [], "terms": [], "followed_org_ids": [],
            "work_type_prefs": {"연구": "positive", "감리": "negative"},
        },
    )
    assert response.status_code == 204
    profile = client.get(f"/api/customers/{customer_a_id}/interests").json()
    assert profile["work_type_prefs"] == {"연구": "positive", "감리": "negative"}
    assert "구매" in profile["work_types"]  # 전체 카탈로그도 같이 내려옴(물품/용역/외자 포함)
    assert "물품" in profile["work_types"]


def test_save_rejects_unknown_work_type(client: TestClient, customer_a_id: int):
    response = client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={"topic_ids": [], "terms": [], "followed_org_ids": [], "work_type_prefs": {"존재하지않는유형": "positive"}},
    )
    assert response.status_code == 400


def test_save_rejects_unknown_work_type_preference(client: TestClient, customer_a_id: int):
    response = client.put(
        f"/api/customers/{customer_a_id}/interests",
        json={"topic_ids": [], "terms": [], "followed_org_ids": [], "work_type_prefs": {"연구": "매우좋음"}},
    )
    assert response.status_code == 400


@pytest.fixture
def two_topic_notices():
    """서로 다른 관심주제에 매칭된 공고 두 건 — 우선순위에 따라 점수가 달라지는지 보려면
    최소 두 개의 서로 다른 topic_id가 필요하다."""
    with engine.connect() as conn:
        from app.models import interest_topic
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topics = conn.execute(select(interest_topic.c.id).order_by(interest_topic.c.id).limit(2)).scalars().all()
    high_topic_id, normal_topic_id = topics[0], topics[1]

    with engine.begin() as conn:
        notice_high = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 우선순위 높음 매칭용",
                url="https://example.grib-test.kr/notice/priority-high",
            ).returning(notice.c.id)
        ).scalar_one()
        notice_normal = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 우선순위 보통 매칭용",
                url="https://example.grib-test.kr/notice/priority-normal",
            ).returning(notice.c.id)
        ).scalar_one()
        # l2_score를 강도 포화 기준(TOPIC_STRENGTH_REFERENCE=10) 이상으로 줘서 매칭 강도가
        # 1.0이 되게 한다(2026-09-08 재설계) — 그래야 우선순위 점수(40/30)가 그대로 나와
        # "우선순위 자체의 상대적 크기"만 비교하는 이 테스트의 취지가 유지된다.
        conn.execute(insert(notice_score).values(notice_id=notice_high, interest_topic_id=high_topic_id, l2_score=12, reason="테스트", rule_ver=1))
        conn.execute(insert(notice_score).values(notice_id=notice_normal, interest_topic_id=normal_topic_id, l2_score=12, reason="테스트", rule_ver=1))

    yield {"high_topic_id": high_topic_id, "normal_topic_id": normal_topic_id, "notice_high": notice_high, "notice_normal": notice_normal}

    with engine.begin() as conn:
        conn.execute(delete(notice_score).where(notice_score.c.notice_id.in_([notice_high, notice_normal])))
        conn.execute(delete(notice).where(notice.c.id.in_([notice_high, notice_normal])))


def test_high_priority_topic_scores_above_normal(two_topic_notices):
    draft = InterestDraft(
        topic_ids=[two_topic_notices["high_topic_id"], two_topic_notices["normal_topic_id"]],
        topic_priorities={two_topic_notices["high_topic_id"]: "high"},
    )
    with engine.connect() as conn:
        scored = _score_all(conn, draft, min_score=0)
    scores_by_notice = {n["id"]: s for n, s, _matched in scored}
    assert scores_by_notice[two_topic_notices["notice_high"]] == 40
    assert scores_by_notice[two_topic_notices["notice_normal"]] == 30
    assert scores_by_notice[two_topic_notices["notice_high"]] > scores_by_notice[two_topic_notices["notice_normal"]]


def test_top_matches_includes_matched_topic_names(two_topic_notices):
    # "이 공고가 왜 관심공고로 떴는지" 화면에 보여주기 위한 topics 필드(2026-09-06 요청,
    # 2026-09-08 강도 라벨 추가) — 고객이 선택한 관심주제 중 실제로 매칭된 것의 이름+강도
    # 라벨이 담겨야 한다. 픽스처가 l2_score=12(포화)로 넣어두므로 "강한 일치"가 기대값.
    with engine.connect() as conn:
        from app.models import interest_topic
        names = dict(conn.execute(select(interest_topic.c.id, interest_topic.c.name)).all())

    draft = InterestDraft(topic_ids=[two_topic_notices["high_topic_id"], two_topic_notices["normal_topic_id"]])
    with engine.connect() as conn:
        matches = top_matches(conn, draft, limit=100, min_score=0)
    by_id = {m["id"]: m for m in matches}

    assert by_id[two_topic_notices["notice_high"]]["topics"] == [f"{names[two_topic_notices['high_topic_id']]}(강한 일치)"]
    assert by_id[two_topic_notices["notice_normal"]]["topics"] == [f"{names[two_topic_notices['normal_topic_id']]}(강한 일치)"]


# ---- 추천 알고리즘 재설계(2026-09-08) — 매칭 강도 × 우선순위, noisy-OR 결합 -----------------


def test_topic_strength_saturates_and_floors():
    assert _topic_strength(TOPIC_STRENGTH_REFERENCE) == 1.0
    assert _topic_strength(TOPIC_STRENGTH_REFERENCE * 5) == 1.0  # 포화 이상은 전부 1.0
    assert _topic_strength(0) == TOPIC_STRENGTH_FLOOR  # 0이어도 바닥값 밑으로는 안 내려감
    assert _topic_strength(TOPIC_STRENGTH_REFERENCE // 2) == 0.5


def test_strength_label_thresholds():
    assert _strength_label(1.0) == "강한 일치"
    assert _strength_label(0.66) == "강한 일치"
    assert _strength_label(0.5) == "보통 일치"
    assert _strength_label(0.2) == "약한 일치"


def test_weak_match_scores_lower_than_strong_match_at_same_priority(two_topic_notices):
    # 우선순위가 같아도(둘 다 미설정 → normal) 매칭 강도가 약하면 점수가 확 낮아져야 한다
    # — "우선순위만 높으면 항상 만점" 이던 예전 방식의 오탐 억제 실패를 고치는 핵심 성질.
    with engine.begin() as conn:
        conn.execute(
            notice_score.update()
            .where(notice_score.c.notice_id == two_topic_notices["notice_normal"])
            .values(l2_score=2)  # 승격 최소 기준 근처 — 약한 신호
        )
    draft = InterestDraft(topic_ids=[two_topic_notices["high_topic_id"], two_topic_notices["normal_topic_id"]])
    with engine.connect() as conn:
        scored = _score_all(conn, draft, min_score=0)
    scores_by_notice = {n["id"]: s for n, s, _matched in scored}
    # notice_high는 l2_score=12(포화, 강도 1.0) → normal 우선순위 만점 30
    # notice_normal은 l2_score=2(강도 0.2) → 30 * 0.2 = 6
    assert scores_by_notice[two_topic_notices["notice_high"]] == 30
    assert scores_by_notice[two_topic_notices["notice_normal"]] == 6
    assert scores_by_notice[two_topic_notices["notice_normal"]] < scores_by_notice[two_topic_notices["notice_high"]]


@pytest.fixture
def dual_topic_notice(two_topic_notices):
    """한 공고가 두 관심주제에 동시에 매칭되는 경우(noisy-OR 결합 검증용) — 기존 두 topic을
    notice_high 하나에 같이 붙인다."""
    notice_id = two_topic_notices["notice_high"]
    with engine.begin() as conn:
        conn.execute(
            insert(notice_score).values(
                notice_id=notice_id, interest_topic_id=two_topic_notices["normal_topic_id"], l2_score=12,
                reason="테스트(2번째 주제)", rule_ver=1,
            )
        )
    yield two_topic_notices
    with engine.begin() as conn:
        conn.execute(
            delete(notice_score).where(
                notice_score.c.notice_id == notice_id,
                notice_score.c.interest_topic_id == two_topic_notices["normal_topic_id"],
            )
        )


def test_multi_topic_match_combines_via_noisy_or_higher_than_either_alone(dual_topic_notice):
    # 두 주제 다 강도 1.0(포화)로 매칭 — high(40)+normal(30) 우선순위가 noisy-OR로 결합되면
    # 1 - (1-0.4)(1-0.3) = 0.58 → 58점. 최고값(40)만 쓰던 예전보다 높아야 하고, 단순 합(70)
    # 보다는 낮아야 한다(diminishing returns).
    draft = InterestDraft(
        topic_ids=[dual_topic_notice["high_topic_id"], dual_topic_notice["normal_topic_id"]],
        topic_priorities={dual_topic_notice["high_topic_id"]: "high"},
    )
    with engine.connect() as conn:
        scored = _score_all(conn, draft, min_score=0)
    scores_by_notice = {n["id"]: s for n, s, _matched in scored}
    combined = scores_by_notice[dual_topic_notice["notice_high"]]
    assert combined == 58
    assert combined > 40  # 최고값 하나만 쓰던 예전 방식보다 높음
    assert combined < 70  # 단순 합보다는 낮음(체감)


# ---- 관심 공고 추천 금액 하한(2026-09-07) ------------------------------------------


@pytest.fixture
def priced_notices():
    """추정가격이 다른 공고 세 건 — 하한선(price_min) 적용 시 각각 다르게 걸러지는지 확인용.
    전부 같은 관심주제에 매칭시켜 topic 조건은 항상 통과하게 두고 가격 필터만 검증한다."""
    with engine.connect() as conn:
        from app.models import interest_topic
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topic_id = conn.execute(select(interest_topic.c.id).order_by(interest_topic.c.id).limit(1)).scalar_one()

    with engine.begin() as conn:
        notice_low = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 가격 하한 미달",
                url="https://example.grib-test.kr/notice/price-low", est_price=10_000_000,
            ).returning(notice.c.id)
        ).scalar_one()
        notice_high = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 가격 하한 충족",
                url="https://example.grib-test.kr/notice/price-high", est_price=100_000_000,
            ).returning(notice.c.id)
        ).scalar_one()
        notice_unknown = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 가격 미공개",
                url="https://example.grib-test.kr/notice/price-unknown", est_price=None,
            ).returning(notice.c.id)
        ).scalar_one()
        ids = [notice_low, notice_high, notice_unknown]
        for nid in ids:
            conn.execute(insert(notice_score).values(notice_id=nid, interest_topic_id=topic_id, l2_score=4, reason="테스트", rule_ver=1))

    yield {"topic_id": topic_id, "notice_low": notice_low, "notice_high": notice_high, "notice_unknown": notice_unknown}

    with engine.begin() as conn:
        conn.execute(delete(notice_score).where(notice_score.c.notice_id.in_(ids)))
        conn.execute(delete(notice).where(notice.c.id.in_(ids)))


def test_price_min_excludes_below_threshold_and_unpriced(priced_notices):
    draft = InterestDraft(topic_ids=[priced_notices["topic_id"]], price_min=50_000_000)
    with engine.connect() as conn:
        scored = _score_all(conn, draft, min_score=0)
    matched_ids = {n["id"] for n, _s, _m in scored}
    assert priced_notices["notice_high"] in matched_ids
    assert priced_notices["notice_low"] not in matched_ids
    assert priced_notices["notice_unknown"] not in matched_ids


def test_price_min_none_includes_everything(priced_notices):
    draft = InterestDraft(topic_ids=[priced_notices["topic_id"]], price_min=None)
    with engine.connect() as conn:
        scored = _score_all(conn, draft, min_score=0)
    matched_ids = {n["id"] for n, _s, _m in scored}
    assert {priced_notices["notice_low"], priced_notices["notice_high"], priced_notices["notice_unknown"]} <= matched_ids


# ---- 이미 마감된 공고는 추천에서 제외(2026-09-12 사용자 발견) ------------------------


@pytest.fixture
def deadline_notices():
    """마감일이 다른 공고 세 건 — 이미 지난 마감일은 추천에서 빠져야 한다. 마감일이 없는
    공고(사전규격 등 실제로도 close_dt가 없는 stage)는 판단 근거가 없어 그대로 포함돼야
    한다. 2026-09-15 — 원래 이 세 번째 예시가 발주계획이었으나, 발주계획 자체가 매칭
    대상에서 제외되면서(_candidate_notices) "마감일 없어도 포함"이라는 이 테스트의 취지와
    맞지 않게 돼 사전규격으로 교체."""
    with engine.connect() as conn:
        from app.models import interest_topic
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topic_id = conn.execute(select(interest_topic.c.id).order_by(interest_topic.c.id).limit(1)).scalar_one()

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        notice_closed = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 이미 마감된 공고",
                url="https://example.grib-test.kr/notice/deadline-closed", close_dt=now - timedelta(days=1),
            ).returning(notice.c.id)
        ).scalar_one()
        notice_open = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", title="[테스트] 아직 마감 전 공고",
                url="https://example.grib-test.kr/notice/deadline-open", close_dt=now + timedelta(days=7),
            ).returning(notice.c.id)
        ).scalar_one()
        notice_no_deadline = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="사전규격", title="[테스트] 마감일 없는 공고",
                url="https://example.grib-test.kr/notice/deadline-none", close_dt=None,
            ).returning(notice.c.id)
        ).scalar_one()
        ids = [notice_closed, notice_open, notice_no_deadline]
        for nid in ids:
            conn.execute(insert(notice_score).values(notice_id=nid, interest_topic_id=topic_id, l2_score=4, reason="테스트", rule_ver=1))

    yield {"topic_id": topic_id, "notice_closed": notice_closed, "notice_open": notice_open, "notice_no_deadline": notice_no_deadline}

    with engine.begin() as conn:
        conn.execute(delete(notice_score).where(notice_score.c.notice_id.in_(ids)))
        conn.execute(delete(notice).where(notice.c.id.in_(ids)))


def test_already_closed_notice_excluded_from_recommendations(deadline_notices):
    draft = InterestDraft(topic_ids=[deadline_notices["topic_id"]])
    with engine.connect() as conn:
        scored = _score_all(conn, draft, min_score=0)
    matched_ids = {n["id"] for n, _s, _m in scored}
    assert deadline_notices["notice_closed"] not in matched_ids
    assert deadline_notices["notice_open"] in matched_ids
    assert deadline_notices["notice_no_deadline"] in matched_ids


# ---- 리포트 2단계 섹션(사전규격·접수예정/입찰접수·접수중, 2026-09-07) ----------------------
# 2026-09-15 — 원래 발주계획까지 3단계였으나, 발주계획은 매칭 신호(l2_score)가 구조적으로
# 약해 사실상 채워지지 않던 자리라 사용자 지시로 리포트 매칭 대상 자체에서 제외했다
# (_candidate_notices 참고). 그래서 _section_of가 "발주계획"을 볼 일이 이제 없다 — 관련
# 단위 테스트는 아래 test_plan_stage_excluded_from_matching으로 대체.


def test_section_of_prenotice_stage():
    assert _section_of({"stage": "사전규격", "channel_name": "나라장터", "open_dt": None, "close_dt": None}) == "prenotice"


def test_section_of_gov_support_not_yet_in_progress_is_prenotice():
    future = datetime.now(timezone.utc) + timedelta(days=3)
    assert _section_of({"stage": "입찰공고", "channel_name": "IRIS", "open_dt": future, "close_dt": None}) == "prenotice"


def test_section_of_gov_support_in_progress_is_active():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    assert _section_of({"stage": "입찰공고", "channel_name": "IRIS", "open_dt": past, "close_dt": None}) == "active"


def test_section_of_public_bid_notice_is_active():
    assert _section_of({"stage": "입찰공고", "channel_name": "나라장터", "open_dt": None, "close_dt": None}) == "active"


def test_section_of_gov_support_closed_is_active_not_prenotice():
    # 실제 리포트에서 발견된 버그(2026-09-07) — 접수 마감(closed)된 정부지원 공고가
    # "!= in_progress" 조건 때문에 "접수예정"으로 잘못 분류되고 있었다.
    past_open = datetime.now(timezone.utc) - timedelta(days=10)
    past_close = datetime.now(timezone.utc) - timedelta(hours=1)
    assert _section_of({"stage": "입찰공고", "channel_name": "IRIS", "open_dt": past_open, "close_dt": past_close}) == "active"


@pytest.fixture
def oversubscribed_prenotice_notices():
    """SECTION_LIMITS["prenotice"]보다 많은 사전규격 공고를 같은 관심주제에 매칭시켜,
    top_matches가 섹션 상한을 실제로 지키는지 확인한다(2026-09-15 — 이 검증에 원래 쓰던
    발주계획 단계가 매칭 대상에서 아예 빠지면서 사전규격으로 교체)."""
    with engine.connect() as conn:
        from app.models import interest_topic
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topic_id = conn.execute(select(interest_topic.c.id).order_by(interest_topic.c.id).limit(1)).scalar_one()

    count = SECTION_LIMITS["prenotice"] + 3
    ids = []
    with engine.begin() as conn:
        for i in range(count):
            nid = conn.execute(
                insert(notice).values(
                    source_id=source_id, source_ver=1, stage="사전규격", title=f"[테스트] 사전규격 초과 테스트 {i}",
                    url=f"https://example.grib-test.kr/notice/prenotice-overflow-{i}",
                ).returning(notice.c.id)
            ).scalar_one()
            conn.execute(insert(notice_score).values(notice_id=nid, interest_topic_id=topic_id, l2_score=4, reason="테스트", rule_ver=1))
            ids.append(nid)

    yield {"topic_id": topic_id, "ids": ids}

    with engine.begin() as conn:
        conn.execute(delete(notice_score).where(notice_score.c.notice_id.in_(ids)))
        conn.execute(delete(notice).where(notice.c.id.in_(ids)))


def test_top_matches_respects_section_limit(oversubscribed_prenotice_notices):
    # 공유 개발 DB라 같은 관심주제에 이미 매칭된 실제 사전규격 공고가 섞여 들어올 수 있어
    # (2026-09-05 등 세션 내내 반복된 이슈) 정확히 상한 개수를 맞히는 대신 "상한을 절대
    # 넘지 않는다"만 확실히 검증한다 — 핵심은 상한(SECTION_LIMITS["prenotice"])보다 많이
    # 넣었는데 그 상한을 넘기지 않는 것.
    draft = InterestDraft(topic_ids=[oversubscribed_prenotice_notices["topic_id"]])
    with engine.connect() as conn:
        matches = top_matches(conn, draft, limit=20, min_score=0)
    prenotice_section_total = [m for m in matches if m["stage"] == "사전규격"]
    assert len(prenotice_section_total) <= SECTION_LIMITS["prenotice"]
    prenotice_matches = [m for m in matches if m["id"] in oversubscribed_prenotice_notices["ids"]]
    assert len(prenotice_matches) > 0  # 최소한 일부는 실제로 뽑혀야 함(전부 밀려나면 안 됨)


def test_plan_stage_excluded_from_matching():
    """발주계획은 관심 매칭·리포트 대상에서 아예 제외한다(2026-09-15 사용자 지시 — "발주계획은
    보고서 자체에서 제외를 하자"). l2_score를 포화시켜 강하게 매칭시켜도 결과에 안 나와야
    "낮은 점수라 우연히 안 뽑힌 것"이 아니라 하드 제외임을 확인할 수 있다."""
    with engine.connect() as conn:
        from app.models import interest_topic
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        topic_id = conn.execute(select(interest_topic.c.id).limit(1)).scalar_one()

    with engine.begin() as conn:
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="발주계획", title="[테스트] 발주계획 제외 검증용",
                url="https://example.grib-test.kr/notice/plan-excluded",
            ).returning(notice.c.id)
        ).scalar_one()
        conn.execute(insert(notice_score).values(notice_id=notice_id, interest_topic_id=topic_id, l2_score=12, reason="테스트", rule_ver=1))

    try:
        draft = InterestDraft(topic_ids=[topic_id])
        with engine.connect() as conn:
            scored = _score_all(conn, draft, min_score=0)
        assert notice_id not in {n["id"] for n, _s, _m in scored}
    finally:
        with engine.begin() as conn:
            conn.execute(delete(notice_score).where(notice_score.c.notice_id == notice_id))
            conn.execute(delete(notice).where(notice.c.id == notice_id))
