"""S1-d 공고 상세(U5). 목록 조립은 notice_query.py, 여긴 단건 조회만."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.models import (
    customer,
    customer_followed_org,
    interest_topic,
    notice,
    notice_score,
    org,
    requirement,
)
from app.services.notice_query import NoticeFilters, grib_customer_id, ordered_ids


def get_notice_detail(conn: Connection, notice_id: int) -> dict | None:
    row = conn.execute(
        select(
            notice.c.id,
            notice.c.notice_no,
            notice.c.title,
            notice.c.stage,
            notice.c.pipeline_stage,
            notice.c.est_price,
            notice.c.region,
            notice.c.open_dt,
            notice.c.close_dt,
            notice.c.url,
            notice.c.assignee_name,
            notice.c.org_id,
            org.c.name.label("org_name"),
        )
        .select_from(notice)
        .join(org, org.c.id == notice.c.org_id, isouter=True)
        .where(notice.c.id == notice_id)
    ).mappings().first()
    if row is None:
        return None

    result = dict(row)
    if result.get("est_price") is not None:
        result["est_price"] = int(result["est_price"])

    scores = conn.execute(
        select(notice_score.c.interest_topic_id, interest_topic.c.name, notice_score.c.l2_score, notice_score.c.reason)
        .join(interest_topic, interest_topic.c.id == notice_score.c.interest_topic_id)
        .where(notice_score.c.notice_id == notice_id)
    ).mappings().all()
    result["scores"] = [dict(s) for s in scores]

    requirements = conn.execute(
        select(requirement.c.id, requirement.c.type, requirement.c.value, requirement.c.we_qualify).where(
            requirement.c.notice_id == notice_id
        )
    ).mappings().all()
    result["requirements"] = [dict(r) for r in requirements]

    grib_id = grib_customer_id(conn)
    is_followed = False
    if grib_id is not None and result["org_id"] is not None:
        is_followed = conn.execute(
            select(customer_followed_org.c.id).where(
                customer_followed_org.c.customer_id == grib_id, customer_followed_org.c.org_id == result["org_id"]
            )
        ).first() is not None
    result["org_followed"] = is_followed

    return result


def get_neighbors(conn: Connection, notice_id: int, filters: NoticeFilters) -> dict:
    ids = ordered_ids(conn, filters)
    if notice_id not in ids:
        return {"prev_id": None, "next_id": None}
    index = ids.index(notice_id)
    return {
        "prev_id": ids[index - 1] if index > 0 else None,
        "next_id": ids[index + 1] if index < len(ids) - 1 else None,
    }


def follow_org(conn: Connection, org_id: int) -> None:
    grib_id = grib_customer_id(conn)
    if grib_id is None:
        return
    exists_row = conn.execute(
        select(customer_followed_org.c.id).where(
            customer_followed_org.c.customer_id == grib_id, customer_followed_org.c.org_id == org_id
        )
    ).first()
    if exists_row is None:
        conn.execute(customer_followed_org.insert().values(customer_id=grib_id, org_id=org_id))
