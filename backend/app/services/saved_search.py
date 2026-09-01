"""저장한 검색 — 고객 단위(S7과 같은 계층, 03절 v0.3)."""

from __future__ import annotations

from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Connection

from app.models import saved_search


def list_saved_searches(conn: Connection, customer_id: int) -> list[dict]:
    rows = conn.execute(
        select(saved_search.c.id, saved_search.c.name, saved_search.c.query_params, saved_search.c.created_at)
        .where(saved_search.c.customer_id == customer_id)
        .order_by(saved_search.c.created_at.desc())
    ).mappings().all()
    return [dict(r) for r in rows]


def create_saved_search(conn: Connection, customer_id: int, name: str, query_params: dict) -> int:
    row = conn.execute(
        insert(saved_search)
        .values(customer_id=customer_id, name=name, query_params=query_params)
        .returning(saved_search.c.id)
    ).one()
    return row.id


def delete_saved_search(conn: Connection, customer_id: int, search_id: int) -> bool:
    result = conn.execute(
        delete(saved_search).where(saved_search.c.id == search_id, saved_search.c.customer_id == customer_id)
    )
    return result.rowcount > 0
