"""S1 공고 탐색(U4) 목록 조회 로직. 라우터(app/api/notices.py)는 얇게, 여기가 본체.

탭 3종(2026-09-01 재구성) — "내 관심"(그립 고객 프로필 기반) · "미처리" · "내 담당" 탭은
빠졌다. 대신 이 화면의 실제 쓰임(수집된 데이터를 단계별로 훑어보기)에 맞춰 공고 단계로
묶었다. 관심주제·발주기관은 탭이 아니라 여전히 다중선택 필터로 존재한다(_apply_filters).
"미처리"(classification_correction 미존재)·"내 담당"(assignee_name) 자체는 데이터로는
남아 있다 — 탭에서만 뺐고, 나중에 필요하면 필터로 되살리면 된다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

from sqlalchemy import Select, and_, exists, func, select
from sqlalchemy.engine import Connection

from app.models import customer, notice, notice_score, org, requirement

SORT_OPTIONS = ("priority", "close_asc", "open_desc", "price_desc", "price_asc")

# "전체"는 조건 없음. 나머지 둘은 notice.stage 값을 묶은 것 — 사전규격/발주계획(나라장터)·
# 공모예고(IRIS 접수예정)는 아직 공식 공고 전 단계, 입찰공고/사업공고는 이미 공식 공고된 단계.
TABS = ("all", "pre_stage", "bid_stage")
DEFAULT_TAB = "bid_stage"
_PRE_STAGE_VALUES = ("사전규격", "발주계획", "공모예고")
_BID_STAGE_VALUES = ("입찰공고", "사업공고")
PAGE_SIZE = 20


@dataclass
class NoticeFilters:
    tab: str = DEFAULT_TAB
    q: str | None = None
    domain_ids: list[int] = field(default_factory=list)
    org_ids: list[int] = field(default_factory=list)
    source_ids: list[int] = field(default_factory=list)
    price_min: int | None = None
    price_max: int | None = None
    regions: list[str] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    biz_types: list[str] = field(default_factory=list)  # 업무구분(물품/용역/공사/외자)
    work_types: list[str] = field(default_factory=list)  # 사업유형(개발/운영/유지보수 등, 근사 추정)
    close_in: int | None = None  # 이 안(일)에 마감
    status: str | None = None  # open/closed
    qualified: bool | None = None
    sort: str = "priority"
    page: int = 1
    size: int = PAGE_SIZE


def grib_customer_id(conn: Connection) -> int | None:
    """(주)그립 자신의 customer 레코드 id — 발주기관 팔로우(notice_detail.follow_org) 등
    "그립 스스로도 고객 #1"(의사결정_로그 9번)인 기능에서 계속 쓰인다. S1 탭이었던 "내 관심"은
    2026-09-01 재구성으로 빠졌지만, 이 조회 자체는 탭과 무관하게 여전히 필요하다."""
    stmt = select(customer.c.id).where(customer.c.plan_tier == "internal").limit(1)
    return conn.execute(stmt).scalar_one_or_none()


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
            notice.c.biz_type,
            notice.c.work_type,
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


def _apply_filters(stmt: Select, filters: NoticeFilters):
    conditions = []

    if filters.tab == "pre_stage":
        conditions.append(notice.c.stage.in_(_PRE_STAGE_VALUES))
    elif filters.tab == "bid_stage":
        conditions.append(notice.c.stage.in_(_BID_STAGE_VALUES))
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

    if filters.biz_types:
        conditions.append(notice.c.biz_type.in_(filters.biz_types))

    if filters.work_types:
        conditions.append(notice.c.work_type.in_(filters.work_types))

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
    priority_sq = _priority_subquery()
    stmt = _base_select(priority_sq)
    stmt = _apply_filters(stmt, filters)

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


def ordered_ids(conn: Connection, filters: NoticeFilters) -> list[int]:
    """S1-d 이전/다음(neighbors)용 — 현재 필터·정렬 기준으로 전체 id 순서를 반환.

    페이지 규모(설계안 기준 연간 수만 건)에서는 전량 조회가 무리 없다. 커지면 그때 윈도우
    함수로 바꾸면 되고, 지금 미리 최적화할 이유는 없다.
    """
    priority_sq = _priority_subquery()
    stmt = select(notice.c.id).select_from(notice).join(priority_sq, priority_sq.c.notice_id == notice.c.id, isouter=True)
    stmt = _apply_filters(stmt, filters)
    stmt = _apply_sort(stmt, filters.sort, priority_sq)
    return [row[0] for row in conn.execute(stmt)]


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
    biz_types = [row[0] for row in conn.execute(select(notice.c.biz_type).distinct().where(notice.c.biz_type.is_not(None)))]
    work_types = [row[0] for row in conn.execute(select(notice.c.work_type).distinct().where(notice.c.work_type.is_not(None)))]

    return {
        "topics": [dict(row) for row in topics],
        "orgs": [dict(row) for row in orgs],
        "sources": [dict(row) for row in sources],
        "stages": stages,
        "regions": regions,
        "biz_types": biz_types,
        "work_types": work_types,
    }
