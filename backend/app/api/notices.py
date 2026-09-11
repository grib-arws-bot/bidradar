"""라우터는 얇게 — 필터 조립·정렬·집계는 app/services/에."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.db import engine
from app.deps import require_auth
from app.services.analysis.structure import (
    LLMNotConfiguredError,
    MODEL_ALIASES,
    StructuringInProgressError,
    get_requirements,
    run_structuring_for_notice,
)
from app.services.analysis_pilot import (
    AnalysisInProgressError,
    UnsupportedSourceError,
    get_latest_extraction,
    run_extraction_pilot,
)
from app.services import audit
from app.services.classification import ClassificationError, record_classification
from app.services.notice_dedup import find_and_mark_superseded
from app.services.notice_detail import follow_org, get_neighbors, get_notice_detail
from app.services.notice_query import DEFAULT_TAB, NoticeFilters, count_tabs, filter_options, list_notices
from app.services.notice_topics import add_topic, remove_topic

router = APIRouter(prefix="/api/notices", tags=["notices"])


def _notice_filters(
    tab: str = Query(DEFAULT_TAB),
    q: str | None = Query(None),
    domain: list[int] = Query(default_factory=list, alias="domain[]"),
    org: list[int] = Query(default_factory=list, alias="org[]"),
    org_category: list[str] = Query(default_factory=list, alias="org_category[]"),
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
    sort: str = Query("notice_date_desc"),  # 공고일 최신순 기본(2026-09-08 사용자 지시)
) -> NoticeFilters:
    return NoticeFilters(
        tab=tab,
        q=q,
        domain_ids=domain,
        org_ids=org,
        org_categories=org_category,
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
    size: int = Query(21, ge=1, le=100),  # 3의 배수(2026-09-07) — notice_query.PAGE_SIZE와 동일
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


@router.post("/dedup/rescan")
def post_dedup_rescan(email: str = Depends(require_auth)) -> dict:
    """동일 발주기관·동일 사업명이 발주계획/사전규격/입찰공고 단계에 중복 등장하면 가장 최근
    공고만 남기고 나머지를 무효화한다(2026-09-06 사용자 지시). 관리자가 눌러서 실행 — 새로
    묶이는 그룹을 사람이 검수할 여지를 두기 위해 자동 실행하지 않는다(S8 원칙 3과 같은 이유)."""
    with engine.begin() as conn:
        result = find_and_mark_superseded(conn)
        audit.record(conn, actor=email, action="notice.dedup_rescan", target_type="notice", target_id=None, detail=result)
    return result


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


@router.post("/{notice_id}/extract")
def post_extract(notice_id: int, _email: str = Depends(require_auth)) -> dict:
    """S8 파일럿(A0+A1만) — 실제 사이트에서 첨부문서를 받아 텍스트만 추출한다. LLM 분석(A2
    이후)은 이번 범위 밖. 지금은 IRIS 공고만 지원(app/services/analysis_pilot.py 참고)."""
    with engine.begin() as conn:
        try:
            return run_extraction_pilot(conn, notice_id)
        except AnalysisInProgressError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except UnsupportedSourceError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{notice_id}/extract")
def get_extract(notice_id: int, _email: str = Depends(require_auth)) -> dict | None:
    with engine.connect() as conn:
        return get_latest_extraction(conn, notice_id)


class StructureRequest(BaseModel):
    model: str = "haiku"  # 구현스펙 07절 — 관리자가 3종(haiku/sonnet/opus) 중 선택, 기본은 비용이 싼 haiku


@router.post("/{notice_id}/structure")
def post_structure(notice_id: int, payload: StructureRequest, _email: str = Depends(require_auth)) -> dict:
    """S8 A2(요구사양 구조화, LLM) — 이미 성공한 A1 추출 결과를 대상으로 요구사양을 뽑아낸다.
    LLM 호출 비용이 발생하므로 관리자가 명시적으로 눌렀을 때만 실행(자동 실행 금지, 원칙 3)."""
    model = MODEL_ALIASES.get(payload.model, payload.model)
    with engine.begin() as conn:
        try:
            return run_structuring_for_notice(conn, notice_id, model=model)
        except StructuringInProgressError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except LLMNotConfiguredError as exc:
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{notice_id}/requirements")
def get_requirements_route(notice_id: int, _email: str = Depends(require_auth)) -> dict | None:
    with engine.connect() as conn:
        return get_requirements(conn, notice_id)


class TopicRequest(BaseModel):
    topic_id: int


@router.post("/{notice_id}/topics")
def post_notice_topic(notice_id: int, payload: TopicRequest, _email: str = Depends(require_auth)) -> dict:
    """상세페이지에서 관심주제를 직접 추가(2026-09-05) — S1 분류검수(classification_correction,
    감사로그용)와는 다르게 notice_score를 그 자리에서 바로 바꾼다."""
    with engine.begin() as conn:
        added = add_topic(conn, notice_id, payload.topic_id)
    return {"added": added}


@router.delete("/{notice_id}/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_notice_topic(notice_id: int, topic_id: int, _email: str = Depends(require_auth)) -> None:
    with engine.begin() as conn:
        remove_topic(conn, notice_id, topic_id)
