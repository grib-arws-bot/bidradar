"""S1 공고 탐색(U4) 목록 조회 로직. 라우터(app/api/notices.py)는 얇게, 여기가 본체.

탭 4종의 실제 의미는 04절 참고 — 단일 계정(03절 v0.3) 전제라 "mine"은 개인이 아니라
그립 고객 레코드(customer.plan_tier='internal')의 관심 카테고리를 뜻한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, and_, exists, func, select
from sqlalchemy.engine import Connection

from app.models import customer, customer_interest, notice, notice_score, org, requirement

SORT_OPTIONS = ("priority", "close_asc", "open_desc", "price_desc", "price_asc")
TABS = ("mine", "all", "untriaged", "assigned")
PAGE_SIZE = 20


@dataclass
class NoticeFilters:
    tab: str = "mine"
    q: str | None = None
    domain_ids: list[int] = field(default_factory=list)
    org_ids: list[int] = field(default_factory=list)
    source_ids: list[int] = field(default_factory=list)
    price_min: int | None = None
    price_max: int | None = None
    regions: list[str] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    close_in: int | None = None  # 이 안(일)에 마감
    status: str | None = None  # open/closed
    qualified: bool | None = None
    sort: str = "priority"
    page: int = 1
    size: int = PAGE_SIZE


def _grib_customer_id(conn: Connection) -> int | None:
    stmt = select(customer.c.id).where(customer.c.plan_tier == "internal").limit(1)
    return conn.execute(stmt).scalar_one_or_none()


def _grib_topic_ids(conn: Connection, grib_id: int | None) -> list[int]:
    if grib_id is None:
        return []
    stmt = select(customer_interest.c.interest_topic_id).where(customer_interest.c.customer_id == grib_id)
    return [row[0] for row in conn.execute(stmt)]


def _priority_subquery():
    return (
        select(notice_score.c.notice_id, func.max(notice_score.c.priority).label("priority"))
        .group_by(notice_score.c.notice_id)
        .subquery()
    )


def _base_select(priority_sq) -> Select:
    return (
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
            org.c.name.label("org_name"),
            priority_sq.c.priority,
        )
        .select_from(notice)
        .join(org, org.c.id == notice.c.org_id, isouter=True)
        .join(priority_sq, priority_sq.c.notice_id == notice.c.id, isouter=True)
    )


def _apply_filters(stmt: Select, filters: NoticeFilters, grib_topic_ids: list[int]):
    conditions = []

    if filters.tab == "mine":
        if not grib_topic_ids:
            # 관심 프로필이 비어 있으면 서비스 레이어가 아니라 라우터가 "전체"로 폴백 처리한다
            # (구현스펙 S1 "빈 상태" 참고) — 여기선 매칭 자체가 불가능하니 빈 결과를 정직하게 반환.
            conditions.append(notice.c.id.is_(None))
        else:
            conditions.append(
                exists().where(
                    and_(notice_score.c.notice_id == notice.c.id, notice_score.c.interest_topic_id.in_(grib_topic_ids))
                )
            )
    elif filters.tab == "untriaged":
        from app.models import classification_correction

        conditions.append(
            ~exists().where(classification_correction.c.notice_id == notice.c.id)
        )
    elif filters.tab == "assigned":
        conditions.append(notice.c.assignee_name.is_not(None))
    # tab == "all" → 조건 없음

    if filters.q:
        like = f"%{filters.q}%"
        conditions.append(notice.c.title.ilike(like))

    if filters.domain_ids:
        conditions.append(
            exists().where(
                and_(notice_score.c.notice_id == notice.c.id, notice_score.c.interest_topic_id.in_(filters.domain_ids))
            )
        )

    if filters.org_ids:
        conditions.append(notice.c.org_id.in_(filters.org_ids))

    if filters.source_ids:
        conditions.append(notice.c.source_id.in_(filters.source_ids))

    if filters.price_min is not None:
        conditions.append(notice.c.est_price >= filters.price_min)
    if filters.price_max is not None:
        conditions.append(notice.c.est_price <= filters.price_max)

    if filters.regions:
        conditions.append(notice.c.region.in_(filters.regions))

    if filters.stages:
        conditions.append(notice.c.stage.in_(filters.stages))

    now = datetime.now(timezone.utc)
    if filters.close_in is not None:
        conditions.append(notice.c.close_dt.is_not(None))
        conditions.append(notice.c.close_dt >= now)
        conditions.append(notice.c.close_dt <= now + timedelta(days=filters.close_in))

    if filters.status == "open":
        conditions.append((notice.c.close_dt.is_(None)) | (notice.c.close_dt >= now))
    elif filters.status == "closed":
        conditions.append(notice.c.close_dt.is_not(None))
        conditions.append(notice.c.close_dt < now)

    if filters.qualified is not None:
        conditions.append(
            exists().where(and_(requirement.c.notice_id == notice.c.id, requirement.c.we_qualify == filters.qualified))
        )

    if conditions:
        stmt = stmt.where(and_(*conditions))
    return stmt


def _apply_sort(stmt: Select, sort: str, priority_sq) -> Select:
    if sort == "close_asc":
        return stmt.order_by(notice.c.close_dt.asc().nulls_last())
    if sort == "open_desc":
        return stmt.order_by(notice.c.open_dt.desc())
    if sort == "price_desc":
        return stmt.order_by(notice.c.est_price.desc().nulls_last())
    if sort == "price_asc":
        return stmt.order_by(notice.c.est_price.asc().nulls_last())
    # 기본값 "priority"
    return stmt.order_by(priority_sq.c.priority.desc().nulls_last(), notice.c.close_dt.asc().nulls_last())


def list_notices(conn: Connection, filters: NoticeFilters) -> tuple[list[dict], int]:
    grib_id = _grib_customer_id(conn)
    grib_topic_ids = _grib_topic_ids(conn, grib_id)

    priority_sq = _priority_subquery()
    stmt = _base_select(priority_sq)
    stmt = _apply_filters(stmt, filters, grib_topic_ids)

    count_stmt = select(func.count()).select_from(stmt.with_only_columns(notice.c.id).subquery())
    total = conn.execute(count_stmt).scalar_one()

    stmt = _apply_sort(stmt, filters.sort, priority_sq)
    page = max(filters.page, 1)
    size = filters.size or PAGE_SIZE
    stmt = stmt.offset((page - 1) * size).limit(size)

    rows = conn.execute(stmt).mappings().all()
    return [_normalize_row(dict(row)) for row in rows], total


def _normalize_row(row: dict) -> dict:
    # SQLAlchemy Numeric -> Decimal -> FastAPI가 문자열로 직렬화해버려 프론트 숫자 비교/정렬이
    # 깨진다. API 경계에서 순수 숫자 타입으로 바꿔둔다.
    if row.get("est_price") is not None:
        row["est_price"] = int(row["est_price"])
    if row.get("priority") is not None:
        row["priority"] = float(row["priority"])
    return row


def count_tabs(conn: Connection) -> dict[str, int]:
    counts = {}
    for tab in TABS:
        _, total = list_notices(conn, NoticeFilters(tab=tab, size=1, page=1))
        counts[tab] = total
    return counts


def has_grib_interests(conn: Connection) -> bool:
    grib_id = _grib_customer_id(conn)
    return bool(_grib_topic_ids(conn, grib_id))


def filter_options(conn: Connection) -> dict:
    """S1 필터 바 드롭다운용 참조 목록. 정식 /api/orgs, /api/admin/sources(U12/U15)와는 별개 —
    지금은 필터 UI 하나만 위한 가벼운 조회."""
    from app.models import interest_topic, source

    topics = conn.execute(
        select(interest_topic.c.id, interest_topic.c.name)
        .where(interest_topic.c.active.is_(True))
        .order_by(interest_topic.c.sort_order)
    ).mappings().all()
    orgs = conn.execute(select(org.c.id, org.c.name).order_by(org.c.name)).mappings().all()
    sources = conn.execute(select(source.c.id, source.c.name).order_by(source.c.name)).mappings().all()
    stages = [row[0] for row in conn.execute(select(notice.c.stage).distinct())]
    regions = [row[0] for row in conn.execute(select(notice.c.region).distinct().where(notice.c.region.is_not(None)))]

    return {
        "topics": [dict(row) for row in topics],
        "orgs": [dict(row) for row in orgs],
        "sources": [dict(row) for row in sources],
        "stages": stages,
        "regions": regions,
    }
