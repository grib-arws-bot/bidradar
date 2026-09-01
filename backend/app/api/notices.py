"""라우터는 얇게 — 필터 조립·정렬·집계는 app/services/notice_query.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.db import engine
from app.deps import require_auth
from app.services.notice_query import NoticeFilters, count_tabs, filter_options, has_grib_interests, list_notices

router = APIRouter(prefix="/api/notices", tags=["notices"])


@router.get("")
def get_notices(
    _email: str = Depends(require_auth),
    tab: str = Query("mine"),
    q: str | None = Query(None),
    domain: list[int] = Query(default_factory=list, alias="domain[]"),
    org: list[int] = Query(default_factory=list, alias="org[]"),
    source: list[int] = Query(default_factory=list, alias="source[]"),
    price_min: int | None = Query(None),
    price_max: int | None = Query(None),
    region: list[str] = Query(default_factory=list, alias="region[]"),
    stage: list[str] = Query(default_factory=list, alias="stage[]"),
    close_in: int | None = Query(None),
    status: str | None = Query(None),
    qualified: bool | None = Query(None),
    sort: str = Query("priority"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> dict:
    # 관심 프로필이 비어 있으면 '내 관심' 대신 전체를 기본으로(S1 빈 상태 원칙) — 서비스 레이어가
    # 아니라 여기서 결정하는 이유는 "탭을 뭘로 보여줄지"가 화면 정책이라 라우터가 알맞기 때문.
    with engine.connect() as conn:
        effective_tab = tab
        if tab == "mine" and not has_grib_interests(conn):
            effective_tab = "all"

        filters = NoticeFilters(
            tab=effective_tab,
            q=q,
            domain_ids=domain,
            org_ids=org,
            source_ids=source,
            price_min=price_min,
            price_max=price_max,
            regions=region,
            stages=stage,
            close_in=close_in,
            status=status,
            qualified=qualified,
            sort=sort,
            page=page,
            size=size,
        )
        items, total = list_notices(conn, filters)

    return {"items": items, "total": total, "page": page, "size": size, "tab": effective_tab}


@router.get("/counts")
def get_notice_counts(_email: str = Depends(require_auth)) -> dict[str, int]:
    with engine.connect() as conn:
        return count_tabs(conn)


@router.get("/filter-options")
def get_filter_options(_email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        return filter_options(conn)
