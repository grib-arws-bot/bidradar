"""라우터는 얇게 — 필터 조립·정렬·집계는 app/services/에."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.db import engine
from app.deps import require_auth
from app.services.classification import ClassificationError, record_classification
from app.services.notice_detail import follow_org, get_neighbors, get_notice_detail
from app.services.notice_query import DEFAULT_TAB, NoticeFilters, count_tabs, filter_options, list_notices

router = APIRouter(prefix="/api/notices", tags=["notices"])


def _notice_filters(
    tab: str = Query(DEFAULT_TAB),
    q: str | None = Query(None),
    domain: list[int] = Query(default_factory=list, alias="domain[]"),
    org: list[int] = Query(default_factory=list, alias="org[]"),
    source: list[int] = Query(default_factory=list, alias="source[]"),
    price_min: int | None = Query(None),
    price_max: int | None = Query(None),
    region: list[str] = Query(default_factory=list, alias="region[]"),
    stage: list[str] = Query(default_factory=list, alias="stage[]"),
    biz_type: list[str] = Query(default_factory=list, alias="biz_type[]"),
    work_type: list[str] = Query(default_factory=list, alias="work_type[]"),
    close_in: int | None = Query(None),
    status_: str | None = Query(None, alias="status"),
    qualified: bool | None = Query(None),
    sort: str = Query("priority"),
) -> NoticeFilters:
    return NoticeFilters(
        tab=tab,
        q=q,
        domain_ids=domain,
        org_ids=org,
        source_ids=source,
        price_min=price_min,
        price_max=price_max,
        regions=region,
        stages=stage,
        biz_types=biz_type,
        work_types=work_type,
        close_in=close_in,
        status=status_,
        qualified=qualified,
        sort=sort,
    )


@router.get("")
def get_notices(
    _email: str = Depends(require_auth),
    filters: NoticeFilters = Depends(_notice_filters),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> dict:
    with engine.connect() as conn:
        filters.page, filters.size = page, size
        items, total = list_notices(conn, filters)

    return {"items": items, "total": total, "page": page, "size": size, "tab": filters.tab}


@router.get("/counts")
def get_notice_counts(_email: str = Depends(require_auth)) -> dict[str, int]:
    with engine.connect() as conn:
        return count_tabs(conn)


@router.get("/filter-options")
def get_filter_options(_email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        return filter_options(conn)


@router.get("/{notice_id}")
def get_notice(notice_id: int, _email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        detail = get_notice_detail(conn, notice_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="공고를 찾을 수 없습니다.")
    return detail


@router.get("/{notice_id}/neighbors")
def get_notice_neighbors(
    notice_id: int, _email: str = Depends(require_auth), filters: NoticeFilters = Depends(_notice_filters)
) -> dict:
    with engine.connect() as conn:
        return get_neighbors(conn, notice_id, filters)


class ClassificationRequest(BaseModel):
    action: str
    categories: list[int] | None = None
    reason: str | None = None


@router.post("/{notice_id}/classification", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def post_classification(
    notice_id: int, payload: ClassificationRequest, _email: str = Depends(require_auth)
) -> None:
    with engine.begin() as conn:
        try:
            record_classification(conn, notice_id, payload.action, payload.categories, payload.reason)
        except ClassificationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/{notice_id}/follow-org", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def post_follow_org(notice_id: int, _email: str = Depends(require_auth)) -> None:
    with engine.begin() as conn:
        detail = get_notice_detail(conn, notice_id)
        if detail is None or detail["org_id"] is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="공고 또는 발주기관을 찾을 수 없습니다.")
        follow_org(conn, detail["org_id"])
