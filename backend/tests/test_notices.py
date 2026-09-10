"""U4 완료조건 검증: 검색 디바운스(프론트 관심사, 여기선 쿼리 파라미터만) · 필터 9종 ·
탭 4종 · 정렬 5종. U2 시드 데이터(120건)를 그대로 사용 — 정확한 개수는 시드 로직이 바뀌면
같이 바뀌므로 하드코딩하지 않고 구조적으로만 검증한다.
"""

from __future__ import annotations

import itertools
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
from sqlalchemy import delete, insert, select

from app.db import engine
from app.main import app
from app.models import analysis, notice, notice_score, source
from app.services.notice_query import SORT_OPTIONS, TABS, NoticeFilters, compute_bid_status, list_notices

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    response = c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    return c


def test_notices_requires_auth():
    anon = TestClient(app)
    response = anon.get("/api/notices")
    assert response.status_code == 401


def test_notices_list_shape(client: TestClient):
    response = client.get("/api/notices", params={"tab": "all", "size": 5})
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {"items", "total", "page", "size", "tab"}
    assert len(body["items"]) <= 5
    assert body["total"] >= len(body["items"])
    if body["items"]:
        item = body["items"][0]
        assert {
            "id", "title", "org_name", "stage", "bid_status", "est_price", "close_dt", "analysis_summary",
            "channel_name", "scores", "notice_type", "notice_status_label", "work_type_label",
        } <= item.keys()
        assert item["notice_type"] in ("공공입찰", "정부지원")


def test_notices_list_includes_latest_analysis_summary(client: TestClient):
    """S8 A2 요약정보(2026-09-05) — summary가 있는 최신 분석만 얹혀야 하고(구버전 summary=NULL인
    분석은 무시), 이 조회 자체는 LLM을 호출하지 않는다."""
    with engine.begin() as conn:
        notice_id = conn.execute(select(notice.c.id).where(notice.c.title.ilike("%CCTV%")).limit(1)).scalar_one()
        conn.execute(
            insert(analysis).values(
                notice_id=notice_id, source_kind="notice", input_ref="x", status="done", ver=1, summary=None,
            )
        )
        conn.execute(
            insert(analysis).values(
                notice_id=notice_id, source_kind="notice", input_ref="x", status="done", ver=2,
                summary={"project_period": "1년", "project_budget": "10억원", "purpose": "테스트", "content_narrative": "테스트 내용"},
            )
        )
    try:
        rows = client.get("/api/notices", params={"tab": "all", "q": "CCTV", "size": 50}).json()["items"]
        row = next(r for r in rows if r["id"] == notice_id)
        assert row["analysis_summary"] == {
            "project_period": "1년", "project_budget": "10억원", "purpose": "테스트", "content_narrative": "테스트 내용",
        }
    finally:
        with engine.begin() as conn:
            conn.execute(delete(analysis).where(analysis.c.notice_id == notice_id))


def test_all_five_tabs_respond(client: TestClient):
    for tab in TABS:
        response = client.get("/api/notices", params={"tab": tab, "size": 1})
        assert response.status_code == 200, tab


def test_default_tab_is_in_progress(client: TestClient):
    # tab 파라미터를 안 주면 백엔드가 DEFAULT_TAB("in_progress")을 쓴다(2026-09-03 재구성 —
    # 생명주기 기준 탭으로 바뀌면서 "입찰접수중"이 기본값).
    response = client.get("/api/notices", params={"size": 1})
    assert response.status_code == 200
    assert response.json()["tab"] == "in_progress"


def test_bid_status_tabs_are_subsets_of_all_and_do_not_overlap(client: TestClient):
    # 2026-09-03 재구성 — 탭이 notice.stage가 아니라 bid_status(생명주기) 기준으로 바뀜.
    # 4개 탭이 서로 안 겹치고, 각 탭에 담긴 공고의 실제 bid_status가 탭 이름과 일치해야 한다.
    all_total = client.get("/api/notices", params={"tab": "all", "size": 1}).json()["total"]
    ids_by_tab: dict[str, set[int]] = {}
    for tab in ("unscheduled", "upcoming", "in_progress", "closed"):
        items = client.get("/api/notices", params={"tab": tab, "size": 50}).json()["items"]
        assert len(items) <= all_total
        assert {i["bid_status"] for i in items} <= {tab}
        ids_by_tab[tab] = {i["id"] for i in items}

    all_ids = ids_by_tab["unscheduled"] | ids_by_tab["upcoming"] | ids_by_tab["in_progress"] | ids_by_tab["closed"]
    for a, b in itertools.combinations(ids_by_tab.values(), 2):
        assert a.isdisjoint(b)
    assert len(all_ids) <= all_total


def test_pagination_pages_do_not_overlap(client: TestClient):
    total = client.get("/api/notices", params={"tab": "all", "size": 1}).json()["total"]
    if total < 11:
        pytest.skip("시드 데이터가 페이지 두 장을 채울 만큼 없음")
    page1 = client.get("/api/notices", params={"tab": "all", "size": 10, "page": 1}).json()["items"]
    page2 = client.get("/api/notices", params={"tab": "all", "size": 10, "page": 2}).json()["items"]
    ids1 = {item["id"] for item in page1}
    ids2 = {item["id"] for item in page2}
    assert ids1.isdisjoint(ids2)


def test_default_page_size_is_multiple_of_three(client: TestClient):
    # 2026-09-07 사용자 지시 — 3열 그리드 보기에서 총 건수가 3의 배수가 아니면 마지막 줄에
    # 빈 칸이 생겨 카드가 빠진 것처럼 보였다. size를 생략하면 3의 배수(21건)가 기본이어야 한다.
    total = client.get("/api/notices", params={"tab": "all", "size": 1}).json()["total"]
    response = client.get("/api/notices", params={"tab": "all"})
    assert response.status_code == 200
    body = response.json()
    expected = min(21, total)
    assert len(body["items"]) == expected
    assert 21 % 3 == 0


def test_search_filters_by_title(client: TestClient):
    response = client.get("/api/notices", params={"tab": "all", "q": "CCTV", "size": 50})
    assert response.status_code == 200
    for item in response.json()["items"]:
        # 대소문자 구분 없이 매칭돼야 한다 — 나라장터 실공고 중 소문자 "cctv" 제목도 있음
        # (2026-09-04 발견, 대문자만 가정했던 이전 검증이 실데이터로 깨짐).
        assert "cctv" in item["title"].lower()


def test_price_range_filter(client: TestClient):
    response = client.get(
        "/api/notices", params={"tab": "all", "price_min": 100_000_000, "price_max": 200_000_000, "size": 50}
    )
    assert response.status_code == 200
    for item in response.json()["items"]:
        if item["est_price"] is not None:
            assert 100_000_000 <= item["est_price"] <= 200_000_000


def test_stage_filter(client: TestClient):
    response = client.get("/api/notices", params={"tab": "all", "stage[]": ["낙찰"], "size": 50})
    assert response.status_code == 200
    for item in response.json()["items"]:
        assert item["stage"] == "낙찰"


def test_biz_type_filter(client: TestClient):
    # 나라장터 물품·공사는 2026-09-05 사용자 지시로 수집 대상에서 완전히 제외(소스 비활성화+
    # 기존 데이터 삭제)돼 실데이터에 biz_type="물품"인 공고가 더 이상 없다 — 필터 자체의
    # 동작만 검증하기 위해 격리된 임시 공고를 하나 넣어서 확인한다.
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="입찰공고", biz_type="물품",
                title="[테스트] biz_type 필터 검증용", url="https://example.grib-test.kr/notice/biz-type-test",
            ).returning(notice.c.id)
        ).scalar_one()
    try:
        response = client.get("/api/notices", params={"tab": "all", "biz_type[]": ["물품"], "size": 50})
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) > 0
        for item in items:
            assert item["biz_type"] == "물품"
    finally:
        with engine.begin() as conn:
            conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_work_type_filter(client: TestClient):
    response = client.get("/api/notices", params={"tab": "all", "work_type[]": ["유지보수"], "size": 50})
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) > 0
    for item in items:
        assert item["work_type"] == "유지보수"


@pytest.mark.parametrize("sort", SORT_OPTIONS)
def test_every_sort_option_returns_200(client: TestClient, sort: str):
    response = client.get("/api/notices", params={"tab": "all", "sort": sort, "size": 20})
    assert response.status_code == 200


def test_sort_close_asc_is_ascending(client: TestClient):
    response = client.get("/api/notices", params={"tab": "all", "sort": "close_asc", "status": "open", "size": 50})
    close_dates = [item["close_dt"] for item in response.json()["items"] if item["close_dt"]]
    assert close_dates == sorted(close_dates)


def test_sort_open_desc_is_descending_with_nulls_last(client: TestClient):
    # 2026-09-07 — PostgreSQL DESC 기본은 NULLS FIRST라 nulls_last()를 안 붙이면 open_dt가
    # 없는 공고(발주계획 등, 의도적으로 비워둠)가 "최신순" 맨 위에 뜨는 반대 결과가 난다.
    response = client.get("/api/notices", params={"tab": "all", "sort": "open_desc", "size": 100})
    items = response.json()["items"]
    open_dates = [item["open_dt"] for item in items]
    non_null = [d for d in open_dates if d]
    assert non_null == sorted(non_null, reverse=True)
    # null이 하나라도 섞여 있으면 전부 non-null 값들 뒤에 와야 한다(앞에 끼어들면 안 됨).
    if None in open_dates and non_null:
        first_null_index = open_dates.index(None)
        assert first_null_index >= len(non_null) - 1 or all(d is not None for d in open_dates[:first_null_index])


def test_default_sort_is_notice_date_desc(client: TestClient):
    # 2026-09-08 사용자 지시 — 공고 탐색 기본 정렬을 게시일 최신순에서 공고일 최신순으로.
    default_response = client.get("/api/notices", params={"tab": "all", "size": 20})
    explicit_response = client.get("/api/notices", params={"tab": "all", "sort": "notice_date_desc", "size": 20})
    default_ids = [item["id"] for item in default_response.json()["items"]]
    explicit_ids = [item["id"] for item in explicit_response.json()["items"]]
    assert default_ids == explicit_ids


def test_sort_notice_date_desc_is_descending_with_nulls_last():
    # "공고일"은 소스별로 extra.ancmDe(IRIS) 또는 extra.nticeDt(발주계획)에 있다(open_dt와는
    # 다른 필드, 2026-09-07 발견) — 둘 다 없는 공고(사전규격 등)는 정렬 맨 뒤로 가야 한다.
    with engine.connect() as conn:
        items, _ = list_notices(conn, NoticeFilters(tab="all", sort="notice_date_desc", size=200))
    notice_dates = [item.get("extra", {}).get("ancmDe") or item.get("extra", {}).get("nticeDt") for item in items]
    non_null = [d for d in notice_dates if d]
    assert non_null == sorted(non_null, reverse=True)
    if None in notice_dates and non_null:
        first_null_index = notice_dates.index(None)
        assert first_null_index >= len(non_null) - 1 or all(d is not None for d in notice_dates[:first_null_index])


def test_notice_counts_shape(client: TestClient):
    response = client.get("/api/notices/counts")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == set(TABS)
    assert all(count >= 0 for count in body.values())


def test_filter_options_shape(client: TestClient):
    response = client.get("/api/notices/filter-options")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"topics", "orgs", "channels", "stages", "regions", "biz_types", "work_types"}
    assert len(body["topics"]) > 0
    assert len(body["orgs"]) > 0
    # "데이터 소스"는 개별 source 행이 아니라 공고기관(나라장터/IRIS 등) 단위로 묶여야 한다
    # (2026-09-05) — 나라장터 소스 6~9개가 각각 따로 나오면 안 됨.
    assert len(body["channels"]) > 0
    channel = body["channels"][0]
    assert {"name", "source_ids"} <= channel.keys()
    assert isinstance(channel["source_ids"], list) and len(channel["source_ids"]) >= 1
    names = [c["name"] for c in body["channels"]]
    assert len(names) == len(set(names))  # 채널명 중복 없음(묶였다는 증거)


# ---- U5: 분류 검수 액션 + S1-d 상세 -------------------------------------------------


def _any_notice_id(client: TestClient) -> int:
    items = client.get("/api/notices", params={"tab": "all", "size": 1}).json()["items"]
    assert items, "시드 데이터에 공고가 있어야 함"
    return items[0]["id"]


def test_notice_detail_200(client: TestClient):
    notice_id = _any_notice_id(client)
    response = client.get(f"/api/notices/{notice_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == notice_id
    assert {"scores", "requirements", "org_followed"} <= body.keys()
    # 공고유형/공고상태/업무구분(2026-09-05) — 채널에 따라 다른 분류 체계를 쓴다.
    assert body["notice_type"] in ("공공입찰", "정부지원")
    assert body["notice_status_label"]
    assert body["work_type_label"]


def test_notice_detail_404(client: TestClient):
    response = client.get("/api/notices/999999999")
    assert response.status_code == 404


def test_classification_confirm(client: TestClient):
    notice_id = _any_notice_id(client)
    response = client.post(f"/api/notices/{notice_id}/classification", json={"action": "confirm"})
    assert response.status_code == 204


def test_classification_recategorize_requires_categories(client: TestClient):
    notice_id = _any_notice_id(client)
    response = client.post(f"/api/notices/{notice_id}/classification", json={"action": "recategorize"})
    assert response.status_code == 422


def test_classification_recategorize_with_categories_succeeds(client: TestClient):
    notice_id = _any_notice_id(client)
    topic_id = client.get("/api/notices/filter-options").json()["topics"][0]["id"]
    response = client.post(
        f"/api/notices/{notice_id}/classification",
        json={"action": "recategorize", "categories": [topic_id]},
    )
    assert response.status_code == 204


def test_classification_irrelevant_requires_reason(client: TestClient):
    notice_id = _any_notice_id(client)
    response = client.post(f"/api/notices/{notice_id}/classification", json={"action": "irrelevant"})
    assert response.status_code == 422

    with_blank_reason = client.post(
        f"/api/notices/{notice_id}/classification", json={"action": "irrelevant", "reason": "   "}
    )
    assert with_blank_reason.status_code == 422


def test_classification_irrelevant_with_reason_succeeds(client: TestClient):
    notice_id = _any_notice_id(client)
    response = client.post(
        f"/api/notices/{notice_id}/classification", json={"action": "irrelevant", "reason": "범위 밖"}
    )
    assert response.status_code == 204


def test_classification_unknown_action_rejected(client: TestClient):
    notice_id = _any_notice_id(client)
    response = client.post(f"/api/notices/{notice_id}/classification", json={"action": "bogus"})
    assert response.status_code == 422


def test_add_notice_topic_then_appears_in_detail(client: TestClient):
    notice_id = _any_notice_id(client)
    topic_id = client.get("/api/notices/filter-options").json()["topics"][0]["id"]
    try:
        response = client.post(f"/api/notices/{notice_id}/topics", json={"topic_id": topic_id})
        assert response.status_code == 200
        assert response.json()["added"] is True

        detail = client.get(f"/api/notices/{notice_id}").json()
        assert any(s["interest_topic_id"] == topic_id for s in detail["scores"])

        # 이미 붙어있으면 added=False(중복 추가 안 됨)
        again = client.post(f"/api/notices/{notice_id}/topics", json={"topic_id": topic_id})
        assert again.json()["added"] is False
    finally:
        with engine.begin() as conn:
            conn.execute(
                delete(notice_score).where(notice_score.c.notice_id == notice_id, notice_score.c.interest_topic_id == topic_id)
            )


def test_remove_notice_topic(client: TestClient):
    notice_id = _any_notice_id(client)
    topic_id = client.get("/api/notices/filter-options").json()["topics"][0]["id"]
    client.post(f"/api/notices/{notice_id}/topics", json={"topic_id": topic_id})

    response = client.delete(f"/api/notices/{notice_id}/topics/{topic_id}")
    assert response.status_code == 204

    detail = client.get(f"/api/notices/{notice_id}").json()
    assert all(s["interest_topic_id"] != topic_id for s in detail["scores"])


def test_neighbors_preserve_filter_and_sort(client: TestClient):
    listing = client.get("/api/notices", params={"tab": "all", "sort": "open_desc", "size": 5}).json()["items"]
    assert len(listing) >= 3
    middle_id = listing[1]["id"]

    response = client.get(
        f"/api/notices/{middle_id}/neighbors", params={"tab": "all", "sort": "open_desc"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["prev_id"] == listing[0]["id"]
    assert body["next_id"] == listing[2]["id"]


def test_follow_org(client: TestClient):
    notice_id = _any_notice_id(client)
    response = client.post(f"/api/notices/{notice_id}/follow-org")
    assert response.status_code == 204
    detail = client.get(f"/api/notices/{notice_id}").json()
    assert detail["org_followed"] is True


# ---- 공고 생명주기 상태(2026-09-03, 사용자 설계) --------------------------------


def test_bid_status_unscheduled_when_no_open_dt():
    now = datetime.now(timezone.utc)
    assert compute_bid_status(None, None, now) == "unscheduled"


def test_bid_status_upcoming_when_open_dt_in_future():
    now = datetime.now(timezone.utc)
    assert compute_bid_status(now + timedelta(days=3), None, now) == "upcoming"


def test_bid_status_in_progress_when_open_dt_passed_and_no_close_dt():
    now = datetime.now(timezone.utc)
    assert compute_bid_status(now - timedelta(days=1), None, now) == "in_progress"


def test_bid_status_in_progress_when_between_open_and_close():
    now = datetime.now(timezone.utc)
    assert compute_bid_status(now - timedelta(days=1), now + timedelta(days=1), now) == "in_progress"


def test_bid_status_closed_when_close_dt_passed():
    now = datetime.now(timezone.utc)
    assert compute_bid_status(now - timedelta(days=10), now - timedelta(days=1), now) == "closed"


def test_bid_status_closed_takes_priority_even_without_open_dt():
    # 방어적 케이스 — 마감일만 있고 시작일이 없는 비정상 데이터도 "마감"을 우선한다.
    now = datetime.now(timezone.utc)
    assert compute_bid_status(None, now - timedelta(days=1), now) == "closed"


# ---- open_dt가 없는 공고는 입찰미정(2026-09-05 발견·수정) ---------------------------
# 사전규격·발주계획·IRIS 공모예고는 정식 입찰 시작일이 아예 없는 단계인데, open_dt가 필수
# 필드였을 때는 "레코드 등록일"을 대신 채워 넣어서 언제나 과거값이 되고 "입찰접수 중"으로
# 잘못 표시됐다(실측: 사전규격 1,284건 중 1,272건). open_dt를 필수에서 빼고(mapper.py)
# 이런 소스는 open_dt를 아예 안 채우도록 고쳤다 — 처음엔 stage 이름으로 강제 고정하는
# 방식을 썼으나, IRIS 접수예정(stage="공모예고")은 실제로 rcveStrDe(접수시작일)라는 진짜
# 미래 날짜가 있어서 그 방식이 오히려 "입찰예정" 표시를 막는 역효과를 냈다(사용자 발견) —
# 그래서 stage 특례를 걷어내고 각 소스의 field_maps에서 진짜 날짜가 있으면 매핑하고 없으면
# 비워두는 방식으로 근본 수정했다(seed_constants.py).


def test_unscheduled_tab_includes_notice_without_open_dt_via_sql(client: TestClient):
    # _bid_status_condition(SQL)이 compute_bid_status(Python)와 어긋나면 탭에서 걸러진 공고와
    # 카드 상태 라벨이 서로 다르게 보이는 사고가 난다(파일 상단 주석 참고) — 실제 API 응답으로
    # SQL 쪽도 같은 규칙을 따르는지 확인한다.
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).limit(1)).scalar_one()
        notice_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, stage="사전규격",
                title="[테스트] 입찰미정 확인용 사전규격 공고",
                open_dt=None, close_dt=None,
                url="https://x/pre-notice-unscheduled-test",
            ).returning(notice.c.id)
        ).scalar_one()
    try:
        # 실데이터가 많아 페이지에 다 안 잡힐 수 있으니(2026-09-04 나라장터 대량 수집 이후)
        # 고유 제목으로 검색해 이 테스트 공고만 좁혀서 확인한다.
        q = "입찰미정 확인용"
        unscheduled = client.get("/api/notices", params={"tab": "unscheduled", "q": q, "size": 20}).json()["items"]
        in_progress = client.get("/api/notices", params={"tab": "in_progress", "q": q, "size": 20}).json()["items"]
        assert notice_id in {i["id"] for i in unscheduled}
        assert notice_id not in {i["id"] for i in in_progress}

        detail = client.get(f"/api/notices/{notice_id}").json()
        assert detail["bid_status"] == "unscheduled"
    finally:
        with engine.begin() as conn:
            conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_notice_list_and_detail_include_bid_status(client: TestClient):
    notice_id = _any_notice_id(client)
    listing = client.get("/api/notices", params={"tab": "all", "size": 1}).json()["items"]
    assert listing[0]["bid_status"] in ("unscheduled", "upcoming", "in_progress", "closed")

    detail = client.get(f"/api/notices/{notice_id}").json()
    assert detail["bid_status"] in ("unscheduled", "upcoming", "in_progress", "closed")
