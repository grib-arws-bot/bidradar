"""notice_dedup.find_and_mark_superseded 검증(2026-09-06) — 동일 발주기관+동일 사업명이
발주계획/사전규격/입찰공고 단계에 중복 등장하면 가장 최근 공고만 유효로 남기고 나머지를
superseded_by_notice_id로 무효화. 목록·매칭 양쪽에서 무효화된 공고가 실제로 빠지는지도 확인.
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
from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import notice, org, source
from app.services.notice_dedup import find_and_mark_superseded
from app.services.notice_query import NoticeFilters, list_notices


@pytest.fixture
def dedup_org():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()
        org_id = conn.execute(
            insert(org).values(name="[테스트] 중복공고정리 발주기관", source_id=source_id).returning(org.c.id)
        ).scalar_one()
    yield org_id, source_id
    with engine.begin() as conn:
        conn.execute(delete(notice).where(notice.c.org_id == org_id))
        conn.execute(delete(org).where(org.c.id == org_id))


def _make_notice(conn, *, org_id: int, source_id: int, title: str, stage: str, open_dt: datetime | None) -> int:
    return conn.execute(
        insert(notice).values(
            source_id=source_id, source_ver=1, org_id=org_id, title=title, stage=stage,
            open_dt=open_dt, url="https://example.test/n",
        ).returning(notice.c.id)
    ).scalar_one()


def test_find_and_mark_superseded_keeps_latest_and_supersedes_rest(dedup_org):
    org_id, source_id = dedup_org
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        plan_id = _make_notice(conn, org_id=org_id, source_id=source_id, title="스마트제조지원 장비 IoT 연계 모니터링 운영 용역", stage="발주계획", open_dt=now - timedelta(days=30))
        prestandard_id = _make_notice(conn, org_id=org_id, source_id=source_id, title="스마트제조지원 장비 IoT 연계 모니터링 운영 용역", stage="사전규격", open_dt=now - timedelta(days=10))
        bid_id = _make_notice(conn, org_id=org_id, source_id=source_id, title="스마트제조지원 장비 IoT 연계 모니터링 운영 용역", stage="입찰공고", open_dt=now - timedelta(days=1))

        result = find_and_mark_superseded(conn)

        rows = {
            r.id: r.superseded_by_notice_id
            for r in conn.execute(select(notice.c.id, notice.c.superseded_by_notice_id).where(notice.c.org_id == org_id))
        }

    assert result["groups_with_duplicates"] >= 1
    assert rows[bid_id] is None  # 가장 최근(입찰공고)이 유효
    assert rows[plan_id] == bid_id
    assert rows[prestandard_id] == bid_id


def test_find_and_mark_superseded_normalizes_whitespace_in_title(dedup_org):
    # 실측(2026-09-06): 같은 사업명인데 중간에 이중 공백만 다른 사례("2026년  스마트 공원...").
    org_id, source_id = dedup_org
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        a = _make_notice(conn, org_id=org_id, source_id=source_id, title="2026년  스마트 공원 안전관리 시스템 유지보수 용역", stage="사전규격", open_dt=now - timedelta(days=5))
        b = _make_notice(conn, org_id=org_id, source_id=source_id, title="2026년 스마트 공원 안전관리 시스템 유지보수 용역", stage="입찰공고", open_dt=now)

        find_and_mark_superseded(conn)

        rows = {
            r.id: r.superseded_by_notice_id
            for r in conn.execute(select(notice.c.id, notice.c.superseded_by_notice_id).where(notice.c.org_id == org_id))
        }
    assert rows[a] == b
    assert rows[b] is None


def test_find_and_mark_superseded_does_not_merge_across_large_date_gap(dedup_org):
    # 매년 반복되는 유지보수 용역처럼 같은 발주기관+같은 사업명이라도 시기가 크게(400일 넘게)
    # 벌어져 있으면 별개 계약으로 보고 묶지 않는다(안전판).
    org_id, source_id = dedup_org
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        old = _make_notice(conn, org_id=org_id, source_id=source_id, title="연간 청소용역", stage="입찰공고", open_dt=now - timedelta(days=800))
        recent = _make_notice(conn, org_id=org_id, source_id=source_id, title="연간 청소용역", stage="입찰공고", open_dt=now)

        find_and_mark_superseded(conn)

        rows = {
            r.id: r.superseded_by_notice_id
            for r in conn.execute(select(notice.c.id, notice.c.superseded_by_notice_id).where(notice.c.org_id == org_id))
        }
    assert rows[old] is None
    assert rows[recent] is None


def test_find_and_mark_superseded_ignores_notices_without_org(dedup_org):
    _org_id, source_id = dedup_org
    with engine.begin() as conn:
        orphan_id = conn.execute(
            insert(notice).values(
                source_id=source_id, source_ver=1, org_id=None, title="발주기관 미상 공고", stage="입찰공고",
                url="https://example.test/orphan",
            ).returning(notice.c.id)
        ).scalar_one()
        try:
            find_and_mark_superseded(conn)
            row = conn.execute(select(notice.c.superseded_by_notice_id).where(notice.c.id == orphan_id)).scalar_one()
            assert row is None
        finally:
            conn.execute(delete(notice).where(notice.c.id == orphan_id))


def test_find_and_mark_superseded_is_idempotent(dedup_org):
    org_id, source_id = dedup_org
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        _make_notice(conn, org_id=org_id, source_id=source_id, title="멱등성 검증용 용역", stage="발주계획", open_dt=now - timedelta(days=20))
        _make_notice(conn, org_id=org_id, source_id=source_id, title="멱등성 검증용 용역", stage="입찰공고", open_dt=now)

        first = find_and_mark_superseded(conn)
        second = find_and_mark_superseded(conn)

    # 새로 만든 공고는 superseded_by_notice_id가 원래 NULL이라, 실제로 값이 바뀌는 건
    # "무효화되는 이전 단계" 1건뿐이다(최신 건은 NULL→NULL이라 변경 없음).
    assert first["notices_updated"] >= 1
    assert second["notices_updated"] == 0  # 이미 반영된 상태라 두 번째 실행은 아무것도 안 바꿈


def test_find_and_mark_superseded_recovers_when_group_shrinks(dedup_org):
    # 이전 실행에서 중복으로 묶였던 공고가, 다른 멤버가 삭제돼 그룹이 1건으로 줄면 다음 재계산
    # 때 superseded_by_notice_id가 다시 NULL로 정리돼야 한다(낡은 포인터가 안 남아야 함).
    org_id, source_id = dedup_org
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        old_id = _make_notice(conn, org_id=org_id, source_id=source_id, title="그룹축소 검증용 용역", stage="발주계획", open_dt=now - timedelta(days=20))
        new_id = _make_notice(conn, org_id=org_id, source_id=source_id, title="그룹축소 검증용 용역", stage="입찰공고", open_dt=now)
        find_and_mark_superseded(conn)
        conn.execute(delete(notice).where(notice.c.id == new_id))

        find_and_mark_superseded(conn)
        remaining = conn.execute(select(notice.c.superseded_by_notice_id).where(notice.c.id == old_id)).scalar_one()
    assert remaining is None


def test_superseded_notice_excluded_from_notice_list_and_counts(dedup_org):
    org_id, source_id = dedup_org
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        old_id = _make_notice(conn, org_id=org_id, source_id=source_id, title="목록제외 검증용 용역", stage="발주계획", open_dt=now - timedelta(days=5))
        new_id = _make_notice(conn, org_id=org_id, source_id=source_id, title="목록제외 검증용 용역", stage="입찰공고", open_dt=now)
        find_and_mark_superseded(conn)

    with engine.connect() as conn:
        items, total = list_notices(conn, NoticeFilters(tab="all", q="목록제외 검증용 용역"))
        ids = {i["id"] for i in items}
    assert new_id in ids
    assert old_id not in ids
    assert total == 1
