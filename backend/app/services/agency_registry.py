"""발주기관(org) 중심 목록 — 관리자 페이지 "소스 관리" 실제 표시 대상(2026-09-01 요청).

"조달청·IRIS는 실제 발주기관이 아니라 공고기관(채널)이다"라는 지적에 따라, 화면은
발주기관(org)을 기준으로 구성하고 그 기관이 어느 채널(소스)로 수집되는지를 붙여
보여준다. source_registry.list_sources()는 채널 자체의 상태를 보는 별도 용도로 남긴다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.engine import Connection

from app.models import org, source, source_run
from app.services.source_registry import ADAPTER_LABELS, COMPLIANCE_WARNING_DAYS

DEFAULT_PAGE_SIZE = 50

# 한글이 영어보다 먼저 나와야 한다(2026-09-01 요청) — 파이썬 정렬 대신 SQL에서 직접 순서를
# 매겨야 페이지네이션(LIMIT/OFFSET)이 전체 정렬 순서와 일치한다(2026-09-05, org 2,396건 규모로
# 커지면서 매 요청 전체를 파이썬 메모리에 올려 정렬하던 방식을 더 못 씀).
_HANGUL_FIRST = case((org.c.name.op("~")("^[가-힣]"), 0), else_=1)

# 화면에 보여줄 status는 원래 파이썬에서 계산했는데(no_source/inactive/no_run_yet/실제상태),
# status 필터+페이지네이션을 SQL에서 같이 하려면 이 계산도 SQL로 옮겨야 한다 — 그대로 옮김.
_STATUS_EXPR = case(
    (source.c.id.is_(None), literal("no_source")),
    (source.c.active.is_(False), literal("inactive")),
    (source_run.c.status.is_(None), literal("no_run_yet")),
    else_=source_run.c.status,
)


def list_agencies(
    conn: Connection,
    *,
    q: str | None = None,
    status: str | None = None,
    category: str | None = None,
    source_id: int | None = None,
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[dict], int]:
    """q: 기관명·약자 부분일치 검색. status/category: 정확히 일치하는 것만. source_id: 특정
    공고기관(채널) 하나에 속한 발주기관만(2026-09-14, "공고기관 중심" 화면의 상세 페이지용).
    (행 목록, 전체 건수)."""
    latest_run_sq = (
        select(source_run.c.source_id, func.max(source_run.c.id).label("latest_id"))
        .group_by(source_run.c.source_id)
        .subquery()
    )
    base = (
        select(
            org.c.id,
            org.c.name,
            org.c.abbr,
            org.c.category,
            org.c.notice_url,
            source.c.name.label("source_name"),
            source.c.channel_name,
            source.c.homepage_url.label("source_homepage_url"),
            source.c.adapter_type,
            source.c.legal_tier,
            source.c.legal_verified_at,
            source_run.c.run_at,
            _STATUS_EXPR.label("row_status"),
        )
        .select_from(org)
        .join(source, source.c.id == org.c.source_id, isouter=True)
        .join(latest_run_sq, latest_run_sq.c.source_id == source.c.id, isouter=True)
        .join(source_run, source_run.c.id == latest_run_sq.c.latest_id, isouter=True)
    )
    if q:
        like = f"%{q}%"
        base = base.where(or_(org.c.name.ilike(like), org.c.abbr.ilike(like)))
    if category:
        base = base.where(org.c.category == category)
    if status:
        base = base.where(_STATUS_EXPR == status)
    if source_id is not None:
        base = base.where(source.c.id == source_id)

    total = conn.execute(select(func.count()).select_from(base.subquery())).scalar_one()

    stmt = base.order_by(_HANGUL_FIRST, org.c.name).offset((page - 1) * size).limit(size)
    rows = conn.execute(stmt).mappings().all()

    now = datetime.now(timezone.utc)
    result = []
    for row in rows:
        verified_at = row["legal_verified_at"]
        # 채널이 아예 없는 발주기관(no_source)은 준법 확인 대상 자체가 아니다 — 경고 배지도 없음.
        compliance_overdue = row["source_name"] is not None and (
            verified_at is None or (now - verified_at) > timedelta(days=COMPLIANCE_WARNING_DAYS)
        )
        result.append(
            {
                "id": row["id"],
                "name": row["name"],
                "abbr": row["abbr"],
                "category": row["category"],
                # 발주기관 자신의 홈페이지 — 2026-09-03엔 "우리가 실제로 아는 건 이 채널이 어디서
                # 공고를 내는가뿐"이라며 org.notice_url을 껐었는데(그때까진 진짜 값이 없어 켜봐야
                # 빈 칸이었음), 2026-09-14 사용자 지시로 발주기관별 실제 영문약자·홈페이지를
                # 조사해 채워넣기 시작하면서 다시 켠다(scripts/backfill_org_info.py 등으로 채움).
                "org_homepage_url": row["notice_url"],
                # 채널(공고기관) 링크 — 위 org_homepage_url이 없는 발주기관은 이걸로 대체 표시.
                "channel_url": row["source_homepage_url"],
                # 2026-09-05 — org_name(운영기관, 나라장터는 전부 "조달청")이 아니라 channel_name
                # ("나라장터")을 쓴다. 공고 탐색 화면의 "데이터 소스" 채널명과 통일하기 위함.
                "channel": row["channel_name"] or row["source_name"],
                "adapter_label": ADAPTER_LABELS.get(row["adapter_type"], row["adapter_type"]) if row["adapter_type"] else None,
                "status": row["row_status"],
                "last_run_at": row["run_at"].isoformat() if row["run_at"] else None,
                # 준법 확인 배지(advisory INBOX #6) — 채널(source) 단위 값을 그대로 보여준다.
                "legal_tier": row["legal_tier"],
                "legal_verified_at": verified_at.isoformat() if verified_at else None,
                "compliance_overdue": compliance_overdue,
            }
        )
    return result, total


def list_agency_channels(conn: Connection) -> list[dict]:
    """공고기관(채널) 목록 — 소스(channel) 하나당 그 안에 등록된 발주기관 수를 붙여 보여준다
    (2026-09-14, "발주기관 현황을 공고기관 중심으로" 요청 — 09-01 결정의 반대 방향 재편.
    이 화면에서 채널 하나를 누르면 list_agencies(source_id=...)로 그 안의 발주기관 목록을 본다)."""
    latest_run_sq = (
        select(source_run.c.source_id, func.max(source_run.c.id).label("latest_id"))
        .group_by(source_run.c.source_id)
        .subquery()
    )
    org_count_sq = (
        select(org.c.source_id, func.count().label("org_count")).group_by(org.c.source_id).subquery()
    )
    stmt = (
        select(
            source.c.id,
            source.c.name,
            source.c.channel_name,
            source.c.homepage_url,
            source.c.adapter_type,
            source.c.legal_tier,
            source.c.legal_verified_at,
            source.c.active,
            source_run.c.status,
            source_run.c.run_at,
            func.coalesce(org_count_sq.c.org_count, 0).label("org_count"),
        )
        .select_from(source)
        .join(latest_run_sq, latest_run_sq.c.source_id == source.c.id, isouter=True)
        .join(source_run, source_run.c.id == latest_run_sq.c.latest_id, isouter=True)
        .join(org_count_sq, org_count_sq.c.source_id == source.c.id, isouter=True)
        .order_by(source.c.channel_name, source.c.name)
    )
    rows = conn.execute(stmt).mappings().all()

    now = datetime.now(timezone.utc)
    result = []
    for row in rows:
        row_status = row["status"] if row["active"] else "inactive"
        if row_status is None:
            row_status = "no_run_yet"
        verified_at = row["legal_verified_at"]
        compliance_overdue = verified_at is None or (now - verified_at) > timedelta(days=COMPLIANCE_WARNING_DAYS)
        result.append(
            {
                "id": row["id"],
                "name": row["name"],
                "channel_name": row["channel_name"] or row["name"],
                "homepage_url": row["homepage_url"],
                "adapter_type": row["adapter_type"],
                "adapter_label": ADAPTER_LABELS.get(row["adapter_type"], row["adapter_type"]),
                "status": row_status,
                "last_run_at": row["run_at"].isoformat() if row["run_at"] else None,
                "legal_tier": row["legal_tier"],
                "legal_verified_at": verified_at.isoformat() if verified_at else None,
                "compliance_overdue": compliance_overdue,
                "org_count": row["org_count"],
            }
        )
    return result


def list_agency_categories(conn: Connection) -> list[str]:
    """분류 드롭다운용 전체 분류 목록 — list_agencies가 페이지네이션되면서(2026-09-05)
    현재 페이지 행에서만 뽑던 방식을 못 쓰게 돼 별도로 뗐다.

    2026-09-11 발견 — DB의 `ORDER BY category`(서버 기본 collation)가 파이썬 `sorted()`
    (유니코드 코드포인트 순서)와 다른 순서를 준다(실측: "R&D 지원기관"이 영문자로 시작하는데도
    DB 정렬에서는 중간에 낌, 한글 항목끼리도 가나다순이 아님). 발주기관 산업분야 분류 백필로
    실제 값이 2~3개에서 12개로 늘면서 처음 드러난 문제 — DB collation에 기대지 않고 애플리케이션
    쪽에서 명시적으로 정렬한다(화면·테스트 양쪽에서 일관된 순서를 보장)."""
    rows = conn.execute(select(org.c.category).where(org.c.category.is_not(None)).distinct()).scalars().all()
    return sorted(rows)
