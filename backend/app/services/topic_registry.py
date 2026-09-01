"""관심주제 대분류(interest_topic, 설계안 L2-b) 관리자 CRUD — 2026-09-01 요청.

customer_interest.get_topic_catalog()은 고객 관심주제 선택 화면용 경량 조회(활성만,
id+name)라 건드리지 않는다. 여기는 관리자가 목록 전체(비활성 포함)를 보고 만들고
고치는 별도 화면용.

**하드 삭제는 만들지 않는다** — keyword_rule·customer_interest·notice_score가 전부
interest_topic_id를 참조하므로, 지우면 참조가 끊긴다. active=false(비활성화)만 제공한다
(소스 레지스트리의 "시스템 소스는 삭제 불가, 비활성화만"과 같은 원칙).
"""

from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.models import interest_topic


class DuplicateTopicNameError(Exception):
    pass


def list_topics(conn: Connection) -> list[dict]:
    rows = conn.execute(
        select(
            interest_topic.c.id,
            interest_topic.c.name,
            interest_topic.c.description,
            interest_topic.c.sort_order,
            interest_topic.c.active,
        ).order_by(interest_topic.c.sort_order, interest_topic.c.id)
    ).mappings().all()
    return [dict(r) for r in rows]


def create_topic(conn: Connection, *, name: str, description: str | None, sort_order: int) -> dict:
    try:
        row = conn.execute(
            insert(interest_topic)
            .values(name=name, description=description, sort_order=sort_order)
            .returning(
                interest_topic.c.id,
                interest_topic.c.name,
                interest_topic.c.description,
                interest_topic.c.sort_order,
                interest_topic.c.active,
            )
        ).mappings().one()
    except IntegrityError as exc:
        raise DuplicateTopicNameError(f"이미 있는 이름입니다: {name}") from exc
    return dict(row)


def update_topic(
    conn: Connection,
    topic_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
    active: bool | None = None,
) -> dict | None:
    values = {
        k: v
        for k, v in {"name": name, "description": description, "sort_order": sort_order, "active": active}.items()
        if v is not None
    }
    if not values:
        row = conn.execute(select(interest_topic).where(interest_topic.c.id == topic_id)).mappings().first()
        return dict(row) if row else None

    try:
        row = conn.execute(
            update(interest_topic)
            .where(interest_topic.c.id == topic_id)
            .values(**values)
            .returning(
                interest_topic.c.id,
                interest_topic.c.name,
                interest_topic.c.description,
                interest_topic.c.sort_order,
                interest_topic.c.active,
            )
        ).mappings().first()
    except IntegrityError as exc:
        raise DuplicateTopicNameError(f"이미 있는 이름입니다: {name}") from exc
    return dict(row) if row else None
