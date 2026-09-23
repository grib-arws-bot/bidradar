"""공고별 행동 데이터(좋아요/클릭/상세보기, 2026-09-23) — 향후 추천 신호
(recommendation_signals.py)로 쓰기 위해 쌓아둔다. audit_log·report_send_log와 같은
append-only 이벤트 로그 관례를 따른다.

좋아요는 별도 상태 테이블을 두지 않고 like/unlike 이벤트로 쌓은 뒤 "가장 최근 이벤트"로
현재 상태를 계산한다 — 상태 테이블과 로그 테이블이 서로 어긋나는 이중 소스 문제를 원천적으로
없앤다. 이 규모(사내 도구)에서 최신 행 하나 찾는 서브쿼리 비용은 무시할 수준이다.

클릭/상세보기는 남용 방지가 아니라 새로고침·React StrictMode 중복 호출로 숫자가 의미 없이
부풀어오르는 걸 막기 위한 짧은 de-dupe 윈도우만 둔다 — 프로젝트 전체에 레이트리밋·CSRF가
어디에도 없고(확인됨), 이 엔드포인트가 하는 일은 INSERT 한 줄뿐이라 남용당해도 손해가
"쓰레기 행 몇 개" 수준이다. 진짜 스크립트 남용이 실측되면 그때 프로젝트 전체 레이트리밋
도입을 별도로 결정한다(이번 스코프 아님).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from app.db import engine
from app.models import notice_engagement_event

DEDUPE_WINDOW_SECONDS = {"view": 300, "click": 5}


def _recent_duplicate(conn: Connection, customer_id: int, notice_id: int, event_type: str, window_seconds: int) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    row = conn.execute(
        select(notice_engagement_event.c.id)
        .where(
            notice_engagement_event.c.customer_id == customer_id,
            notice_engagement_event.c.notice_id == notice_id,
            notice_engagement_event.c.event_type == event_type,
            notice_engagement_event.c.created_at >= cutoff,
        )
        .limit(1)
    ).first()
    return row is not None


def _record_event(customer_id: int, notice_id: int, report_id: int | None, event_type: str) -> None:
    window_seconds = DEDUPE_WINDOW_SECONDS.get(event_type)
    with engine.begin() as conn:
        if window_seconds is not None and _recent_duplicate(conn, customer_id, notice_id, event_type, window_seconds):
            return
        conn.execute(
            insert(notice_engagement_event).values(
                customer_id=customer_id, notice_id=notice_id, report_id=report_id, event_type=event_type,
            )
        )


def record_click(customer_id: int, notice_id: int, report_id: int | None = None) -> None:
    _record_event(customer_id, notice_id, report_id, "click")


def record_view(customer_id: int, notice_id: int, report_id: int | None = None) -> None:
    _record_event(customer_id, notice_id, report_id, "view")


def get_like_state(conn: Connection, customer_id: int, notice_id: int) -> bool:
    """(customer_id, notice_id)의 like/unlike 이벤트 중 가장 최근 것이 'like'인지. 이벤트가
    아예 없으면 False(좋아요 안 한 것과 동일하게 취급)."""
    latest = conn.execute(
        select(notice_engagement_event.c.event_type)
        .where(
            notice_engagement_event.c.customer_id == customer_id,
            notice_engagement_event.c.notice_id == notice_id,
            notice_engagement_event.c.event_type.in_(("like", "unlike")),
        )
        .order_by(notice_engagement_event.c.created_at.desc(), notice_engagement_event.c.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return latest == "like"


def set_like(customer_id: int, notice_id: int, report_id: int | None, liked: bool) -> bool:
    """멱등 — 이미 원하는 상태면 새 이벤트를 안 쌓는다(중복 클릭·재시도에도 안전). 반환값은
    적용된 상태(요청한 liked 그대로)."""
    with engine.begin() as conn:
        if get_like_state(conn, customer_id, notice_id) == liked:
            return liked
        conn.execute(
            insert(notice_engagement_event).values(
                customer_id=customer_id, notice_id=notice_id, report_id=report_id,
                event_type="like" if liked else "unlike",
            )
        )
    return liked
