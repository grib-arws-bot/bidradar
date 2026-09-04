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

from app.models import analysis, customer, notice, notice_score, org, requirement, source

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


# 2026-09-05 — 처음엔 "사전규격/발주계획/공모예고 단계는 항상 unscheduled로 고정"하는
# stage 기반 예외를 뒀었는데, IRIS 접수예정(stage="공모예고")이 실제로는 rcveStrDe(접수시작일)
# 라는 진짜 미래 날짜를 갖고 있어서 그 규칙이 오히려 IRIS 접수예정의 "입찰예정" 표시를 막는
# 역효과를 냈다(사용자 발견). 근본 원인(각 소스가 open_dt에 "레코드 등록일"을 넣어 항상
# 과거값이 되는 것)을 field_maps 단에서 고쳤다 — 진짜 미래 시작일이 있는 소스(나라장터
# 입찰공고의 bidBeginDt, IRIS 접수예정의 rcveStrDe)는 그 필드를 쓰고, 그런 필드 자체가 없는
# 소스(사전규격·발주계획·IRIS 공모예고)는 open_dt를 아예 비워둔다. open_dt가 없으면 아래
# 로직이 자연히 "unscheduled"로 분류하므로 stage 기반 특례가 더 이상 필요 없다.


def compute_bid_status(open_dt: datetime | None, close_dt: datetime | None, now: datetime) -> str:
    if close_dt is not None and close_dt <= now:
        return "closed"
    if open_dt is None:
        return "unscheduled"
    if open_dt > now:
        return "upcoming"
    return "in_progress"


def _bid_status_condition(bid_status: str, now: datetime):
    """compute_bid_status()와 동일한 우선순위를 SQL WHERE 조건으로 옮긴 것 — 탭 필터링에 쓴다."""
    not_closed = notice.c.close_dt.is_(None) | (notice.c.close_dt > now)
    if bid_status == "closed":
        return notice.c.close_dt.is_not(None) & (notice.c.close_dt <= now)
    if bid_status == "unscheduled":
        return not_closed & notice.c.open_dt.is_(None)
    if bid_status == "upcoming":
        return not_closed & notice.c.open_dt.is_not(None) & (notice.c.open_dt > now)
    if bid_status == "in_progress":
        return not_closed & notice.c.open_dt.is_not(None) & (notice.c.open_dt <= now)
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


def _latest_analysis_summary_subquery():
    """공고 목록 카드에 "요약정보"(사업기간·사업비·과제목표·과제내용)를 얹기 위한 서브쿼리 —
    S8 A2가 아직 실행 안 된 공고가 대부분이라(파일럿, 관리자가 건별로 실행) summary가 NULL인
    분석은 애초에 제외해 최신 유효 분석만 남긴다. 이 조인은 새 LLM 호출을 만들지 않는다 —
    이미 저장된 값을 보여줄 뿐."""
    latest_ver_sq = (
        select(analysis.c.notice_id, func.max(analysis.c.ver).label("max_ver"))
        .where(analysis.c.summary.is_not(None))
        .group_by(analysis.c.notice_id)
        .subquery()
    )
    return (
        select(analysis.c.notice_id, analysis.c.summary)
        .select_from(analysis)
        .join(
            latest_ver_sq,
            and_(analysis.c.notice_id == latest_ver_sq.c.notice_id, analysis.c.ver == latest_ver_sq.c.max_ver),
        )
        .subquery()
    )


def _base_select(priority_sq) -> Select:
    summary_sq = _latest_analysis_summary_subquery()
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
            source.c.channel_name,
            priority_sq.c.priority,
            summary_sq.c.summary.label("analysis_summary"),
        )
        .select_from(notice)
        .join(org, org.c.id == notice.c.org_id, isouter=True)
        .join(source, source.c.id == notice.c.source_id, isouter=True)
        .join(priority_sq, priority_sq.c.notice_id == notice.c.id, isouter=True)
        .join(summary_sq, summary_sq.c.notice_id == notice.c.id, isouter=True)
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
    row["bid_status"] = compute_bid_status(row.get("open_dt"), row.get("close_dt"), datetime.now(timezone.utc))
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
    from app.models import interest_topic

    topics = conn.execute(
        select(interest_topic.c.id, interest_topic.c.name)
        .where(interest_topic.c.active.is_(True))
        .order_by(interest_topic.c.sort_order)
    ).mappings().all()
    orgs = conn.execute(select(org.c.id, org.c.name).order_by(org.c.name)).mappings().all()
    # "데이터 소스" 필터(2026-09-05)는 개별 source 행이 아니라 공고기관(channel_name) 단위로
    # 묶어서 보여준다 — 나라장터 하나만 봐도 사전규격·발주계획·입찰공고 3종×물품/용역/공사로
    # 9개 행이 나와 관리자가 아닌 일반 사용자에게는 지나치게 세분화돼 있었다.
    source_rows = conn.execute(select(source.c.id, source.c.channel_name).order_by(source.c.channel_name)).all()
    channel_ids: dict[str, list[int]] = {}
    for source_id, channel_name in source_rows:
        channel_ids.setdefault(channel_name, []).append(source_id)
    channels = [{"name": name, "source_ids": ids} for name, ids in sorted(channel_ids.items())]
    stages = [row[0] for row in conn.execute(select(notice.c.stage).distinct())]
    regions = [row[0] for row in conn.execute(select(notice.c.region).distinct().where(notice.c.region.is_not(None)))]
    biz_types = [row[0] for row in conn.execute(select(notice.c.biz_type).distinct().where(notice.c.biz_type.is_not(None)))]
    work_types = [row[0] for row in conn.execute(select(notice.c.work_type).distinct().where(notice.c.work_type.is_not(None)))]

    return {
        "topics": [dict(row) for row in topics],
        "orgs": [dict(row) for row in orgs],
        "channels": channels,
        "stages": stages,
        "regions": regions,
        "biz_types": biz_types,
        "work_types": work_types,
    }
