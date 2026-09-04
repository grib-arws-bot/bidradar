"""S1 공고 탐색(U4) 목록 조회 로직. 라우터(app/api/notices.py)는 얇게, 여기가 본체.

탭(2026-09-03 재구성, 2번째) — "내 관심"·"미처리"·"내 담당"은 애초에 빠졌고(2026-09-01),
처음엔 stage(어느 소스에서 왔는가) 기준 2분류(사전규격·발주계획·공모예고 / 입찰공고·사업공고)
였다가, 공고 생명주기 상태(bid_status) 기준으로 다시 바꿨다. IRIS 접수예정 공고를 실사이트와
대조하다가 "소스명은 접수예정인데 실제로는 접수중"인 경우를 발견한 게 계기 — 탭도 그 생명주기
(입찰미정→입찰예정→입찰접수→입찰마감)를 그대로 반영해야 사용자가 보는 탭 이름과 실제 공고
상태가 어긋나지 않는다. 관심주제·발주기관·stage 자체는 탭이 아니라 여전히 다중선택 필터로
존재한다(_apply_filters).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

from sqlalchemy import Select, and_, exists, func, select
from sqlalchemy.engine import Connection

from app.models import customer, notice, notice_score, org, requirement

SORT_OPTIONS = ("priority", "close_asc", "open_desc", "price_desc", "price_asc")

# notice.stage는 "어느 수집 단계(소스)에서 왔는가"만 나타낸다 — 사전규격/발주계획/공모예고로
# 들어온 공고도 시간이 지나면 접수가 시작되고 마감되지만, stage 자체는 안 바뀐다(수집 시점에
# 한 번 고정). open_dt/close_dt와 현재 시각만으로 매 조회 시점에 다시 계산하는 생명주기
# 상태를 별도로 둔다(사용자 설계):
#   1) unscheduled — 시작일 자체가 아직 미확정
#   2) upcoming    — 시작일은 있으나 아직 도래 안 함
#   3) in_progress — 시작일이 지났고(또는 애초에 없고) 마감 전
#   4) closed      — 마감일이 지남
# stage(수집 단계 분류)와는 독립된 축이라 나라장터·IRIS·K-water 등 소스에 상관없이 동일하게
# 적용된다. DB 컬럼으로 저장하지 않는다 — "지금 몇 시인가"에 따라 매번 다시 계산되는 값을
# 저장하면 시간이 지나며 값이 실제와 어긋나는(stale) 문제가 반복될 뿐이다.
BID_STATUSES = ("unscheduled", "upcoming", "in_progress", "closed")

# "전체"는 조건 없음. 나머지 4개는 아래 bid_status 정의와 반드시 같은 우선순위로 판정해야
# 한다 — compute_bid_status()(단건, Python)와 _bid_status_condition()(목록 필터링, SQL)가
# 서로 어긋나면 탭에서 걸러진 공고와 카드에 찍히는 상태 라벨이 달라지는 사고가 난다.
TABS = ("all",) + BID_STATUSES
DEFAULT_TAB = "in_progress"


# 2026-09-05 발견 — 사전규격/발주계획/공모예고는 아직 정식 입찰이 시작되지 않은 단계인데,
# 이 단계의 open_dt/close_dt는 "입찰 시작/마감"이 아니라 그 레코드 자체의 등록·게시일(사전규격
# 접수개시일, 발주계획 등록일, IRIS 공고일)이다 — 레코드가 존재하는 한 이 값은 항상 채워져
# 있어서(REQUIRED_FIELDS가 open_dt를 강제) "입찰미정"이 한 건도 안 나오고, 실제로는 사전규격
# 1,284건 중 1,272건이 "입찰접수 중"으로 잘못 표시되고 있었다(사용자 발견). 이 3단계는 정식
# 입찰일 자체가 없는 게 맞으므로 open_dt/close_dt와 무관하게 항상 unscheduled로 고정한다
# (사용자 확정) — 입찰공고·사업공고 단계로 넘어가야 비로소 실제 입찰 일정을 갖는다.
PRE_NOTICE_STAGES = frozenset({"사전규격", "발주계획", "공모예고"})


def compute_bid_status(
    open_dt: datetime | None, close_dt: datetime | None, now: datetime, stage: str | None = None
) -> str:
    if stage in PRE_NOTICE_STAGES:
        return "unscheduled"
    if close_dt is not None and close_dt <= now:
        return "closed"
    if open_dt is None:
        return "unscheduled"
    if open_dt > now:
        return "upcoming"
    return "in_progress"


def _bid_status_condition(bid_status: str, now: datetime):
    """compute_bid_status()와 동일한 우선순위를 SQL WHERE 조건으로 옮긴 것 — 탭 필터링에 쓴다."""
    is_pre_notice = notice.c.stage.in_(PRE_NOTICE_STAGES)
    not_closed = notice.c.close_dt.is_(None) | (notice.c.close_dt > now)
    if bid_status == "closed":
        return ~is_pre_notice & notice.c.close_dt.is_not(None) & (notice.c.close_dt <= now)
    if bid_status == "unscheduled":
        return is_pre_notice | (not_closed & notice.c.open_dt.is_(None))
    if bid_status == "upcoming":
        return ~is_pre_notice & not_closed & notice.c.open_dt.is_not(None) & (notice.c.open_dt > now)
    if bid_status == "in_progress":
        return ~is_pre_notice & not_closed & notice.c.open_dt.is_not(None) & (notice.c.open_dt <= now)
    raise ValueError(f"알 수 없는 bid_status: {bid_status}")
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
            notice.c.extra,
            org.c.name.label("org_name"),
            priority_sq.c.priority,
        )
        .select_from(notice)
        .join(org, org.c.id == notice.c.org_id, isouter=True)
        .join(priority_sq, priority_sq.c.notice_id == notice.c.id, isouter=True)
    )


def _apply_filters(stmt: Select, filters: NoticeFilters):
    conditions = []
    now = datetime.now(timezone.utc)

    if filters.tab in BID_STATUSES:
        conditions.append(_bid_status_condition(filters.tab, now))
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
    # 2026-09-04 — 정렬 기준에 notice.id를 마지막 동점 처리 기준으로 항상 붙인다. 나라장터
    # 대량 수집(수천 건)으로 close_dt·priority 등이 동일한 행이 흔해지면서, id 없이 정렬하면
    # Postgres가 동점 행의 순서를 매 쿼리마다 다르게 줄 수 있어(정렬 안정성 미보장) 페이지네이션
    # 시 같은 공고가 두 페이지에 겹쳐 나오는 문제가 실측으로 드러났다(20,000여 건 규모에서 재현).
    if sort == "close_asc":
        return stmt.order_by(notice.c.close_dt.asc().nulls_last(), notice.c.id.asc())
    if sort == "open_desc":
        return stmt.order_by(notice.c.open_dt.desc(), notice.c.id.asc())
    if sort == "price_desc":
        return stmt.order_by(notice.c.est_price.desc().nulls_last(), notice.c.id.asc())
    if sort == "price_asc":
        return stmt.order_by(notice.c.est_price.asc().nulls_last(), notice.c.id.asc())
    # 기본값 "priority"
    return stmt.order_by(
        priority_sq.c.priority.desc().nulls_last(), notice.c.close_dt.asc().nulls_last(), notice.c.id.asc()
    )


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
    row["bid_status"] = compute_bid_status(
        row.get("open_dt"), row.get("close_dt"), datetime.now(timezone.utc), row.get("stage")
    )
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
