"""공고 보존 정책(2026-09-04) — app/services/notice_cleanup.py 검증. 마감 후
retention_days가 지난 공고만 삭제하고, 마감일이 없거나 아직 안 지난 공고·연관 행(analysis·
award)까지 올바르게 정리되는지 확인한다."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")
os.environ.setdefault("ADMIN_EMAIL", "report@grib.co.kr")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$argon2id$v=19$m=65536,t=3,p=4$9/7/Wg+VSkOsVCeiQiCz7w$bdDzJi9bKuERjBb6NHN0Ztk+X6uwxugL7kViHVRiqnY",
)

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, insert, select

from app.db import engine
from app.models import analysis, award, notice, source
from app.services.notice_cleanup import NO_CLOSE_RETENTION_DAYS, delete_expired_notices

_NOW = datetime.now(timezone.utc)


def _make_notice(conn, source_id: int, *, close_dt, title: str, open_dt=None, extra=None) -> int:
    return conn.execute(
        insert(notice).values(
            source_id=source_id, source_ver=1, stage="입찰공고", title=title,
            open_dt=open_dt if open_dt is not None else _NOW - timedelta(days=10), close_dt=close_dt,
            url=f"https://x/{title}", extra=extra,
        ).returning(notice.c.id)
    ).scalar_one()


def test_delete_expired_notices_removes_only_past_retention_window():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()
        long_closed = _make_notice(conn, source_id, close_dt=_NOW - timedelta(days=40), title="40일전마감_삭제대상")
        recently_closed = _make_notice(conn, source_id, close_dt=_NOW - timedelta(days=5), title="5일전마감_유예기간")
        still_open = _make_notice(conn, source_id, close_dt=_NOW + timedelta(days=5), title="진행중_보존")
        no_close_dt = _make_notice(conn, source_id, close_dt=None, title="마감일없음_보존")

    try:
        with engine.begin() as conn:
            deleted = delete_expired_notices(conn, retention_days=30)

        with engine.connect() as conn:
            remaining_ids = {
                row.id
                for row in conn.execute(
                    select(notice.c.id).where(
                        notice.c.id.in_([long_closed, recently_closed, still_open, no_close_dt])
                    )
                )
            }
    finally:
        with engine.begin() as conn:
            conn.execute(
                delete(notice).where(notice.c.id.in_([long_closed, recently_closed, still_open, no_close_dt]))
            )

    # deleted는 DB 전체(다른 시드·이전 테스트 데이터 포함)의 만료 건수라 정확한 값을 단정할 수
    # 없다 — 최소 우리가 넣은 1건(long_closed)은 포함돼 있어야 한다는 것만 확인.
    assert deleted >= 1
    assert remaining_ids == {recently_closed, still_open, no_close_dt}


def test_delete_expired_notices_cleans_up_non_cascading_analysis_and_award_rows():
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()
        expired_id = _make_notice(conn, source_id, close_dt=_NOW - timedelta(days=40), title="마감_분석기록보유")
        analysis_id = conn.execute(
            insert(analysis).values(notice_id=expired_id, source_kind="notice", input_ref="x", status="done", ver=1)
            .returning(analysis.c.id)
        ).scalar_one()
        conn.execute(insert(award).values(notice_id=expired_id, winner_name="테스트낙찰사"))

    try:
        with engine.begin() as conn:
            deleted = delete_expired_notices(conn, retention_days=30)

        with engine.connect() as conn:
            notice_gone = conn.execute(select(notice.c.id).where(notice.c.id == expired_id)).first() is None
            analysis_gone = conn.execute(select(analysis.c.id).where(analysis.c.id == analysis_id)).first() is None
    finally:
        # 위에서 이미 지워졌을 수 있으니 남아있으면만 정리
        with engine.begin() as conn:
            conn.execute(delete(award).where(award.c.notice_id == expired_id))
            conn.execute(delete(analysis).where(analysis.c.notice_id == expired_id))
            conn.execute(delete(notice).where(notice.c.id == expired_id))

    assert deleted >= 1
    assert notice_gone is True
    assert analysis_gone is True


def test_delete_expired_notices_removes_no_close_dt_past_notice_date_retention():
    """마감일이 없는 공고(발주계획·사전규격·IRIS 등)는 close_dt 대신 "공고일"
    (extra.ancmDe/nticeDt, 둘 다 없으면 open_dt)이 no_close_retention_days를 넘으면 삭제된다."""
    with engine.begin() as conn:
        source_id = conn.execute(select(source.c.id).order_by(source.c.id).limit(1)).scalar_one()
        old_ancm = _make_notice(
            conn, source_id, close_dt=None, title="IRIS_공고일오래됨_삭제대상",
            open_dt=_NOW - timedelta(days=200), extra={"ancmDe": "2020-01-01"},
        )
        recent_ancm = _make_notice(
            conn, source_id, close_dt=None, title="IRIS_공고일최근_보존",
            open_dt=_NOW - timedelta(days=200), extra={"ancmDe": (_NOW - timedelta(days=5)).strftime("%Y-%m-%d")},
        )
        old_open_dt_only = _make_notice(
            conn, source_id, close_dt=None, title="사전규격_공고일필드없음_게시일로판단_삭제대상",
            open_dt=_NOW - timedelta(days=NO_CLOSE_RETENTION_DAYS + 10), extra=None,
        )

    ids = [old_ancm, recent_ancm, old_open_dt_only]
    try:
        with engine.begin() as conn:
            deleted = delete_expired_notices(conn)

        with engine.connect() as conn:
            remaining_ids = {row.id for row in conn.execute(select(notice.c.id).where(notice.c.id.in_(ids)))}
    finally:
        with engine.begin() as conn:
            conn.execute(delete(notice).where(notice.c.id.in_(ids)))

    assert deleted >= 2
    assert remaining_ids == {recent_ancm}
