from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.collector.runner import CollectionInProgressError, run_source_and_process_pending
from app.db import engine
from app.deps import require_auth
from app.services import audit
from app.services.agency_registry import (
    DEFAULT_PAGE_SIZE,
    list_agencies,
    list_agency_categories,
    list_agency_channels,
)
from app.services.source_registry import (
    ScheduleTimesError,
    list_sources,
    set_active,
    set_auto_analyze,
    set_auto_extract,
    set_schedule_times,
)

router = APIRouter(prefix="/api/admin/sources", tags=["sources"])


class AutoExtractUpdate(BaseModel):
    auto_extract: bool


class ActiveUpdate(BaseModel):
    active: bool


class AutoAnalyzeUpdate(BaseModel):
    auto_analyze: bool


class ScheduleTimesUpdate(BaseModel):
    schedule_times: list[str]


@router.get("")
def get_sources_route(_email: str = Depends(require_auth)) -> list[dict]:
    with engine.connect() as conn:
        return list_sources(conn)


@router.patch("/{source_id}/auto-extract")
def update_auto_extract_route(
    source_id: int, payload: AutoExtractUpdate, email: str = Depends(require_auth)
) -> dict:
    """S8 파일럿(첨부문서 자동 다운로드+추출) 자동 실행 여부 — 관리자가 소스별로 켜고 끈다
    (CLAUDE.md S8 원칙 3 "자동 실행 금지"와 충돌 없음 — 시스템이 아니라 관리자가 정하는
    명시적 설정이라 "사용자가 지정"에 해당한다)."""
    with engine.begin() as conn:
        found = set_auto_extract(conn, source_id, payload.auto_extract)
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="소스를 찾을 수 없습니다.")
        audit.record(
            conn, actor=email, action="source.auto_extract", target_type="source", target_id=source_id,
            detail={"auto_extract": payload.auto_extract},
        )
    return {"id": source_id, "auto_extract": payload.auto_extract}


@router.patch("/{source_id}/active")
def update_active_route(source_id: int, payload: ActiveUpdate, email: str = Depends(require_auth)) -> dict:
    """공고 자동 수집 on/off(2026-09-05) — 실제 수집 관문(app/collector/runner.py run_source)이
    이 값을 확인해서 꺼진 소스는 수집을 거부한다(체크박스로 안 끝나는 강제)."""
    with engine.begin() as conn:
        found = set_active(conn, source_id, payload.active)
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="소스를 찾을 수 없습니다.")
        audit.record(
            conn, actor=email, action="source.active", target_type="source", target_id=source_id,
            detail={"active": payload.active},
        )
    return {"id": source_id, "active": payload.active}


@router.patch("/{source_id}/auto-analyze")
def update_auto_analyze_route(
    source_id: int, payload: AutoAnalyzeUpdate, email: str = Depends(require_auth)
) -> dict:
    """S8 A2(요구사양 구조화, LLM 실제 호출·비용 발생) 자동 실행 여부 — auto_extract가 실제로
    성공했을 때만, 항상 Haiku로만 이어서 실행한다(app/collector/runner.py run_source). 관리자가
    이 화면에서 소스별로 명시적으로 켜는 설정이라 CLAUDE.md 원칙 3("자동 실행 금지")과 충돌하지
    않는다고 판단(2026-09-05 사용자 확정, auto_extract와 같은 논리)."""
    with engine.begin() as conn:
        found = set_auto_analyze(conn, source_id, payload.auto_analyze)
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="소스를 찾을 수 없습니다.")
        audit.record(
            conn, actor=email, action="source.auto_analyze", target_type="source", target_id=source_id,
            detail={"auto_analyze": payload.auto_analyze},
        )
    return {"id": source_id, "auto_analyze": payload.auto_analyze}


@router.patch("/{source_id}/schedule")
def update_schedule_route(source_id: int, payload: ScheduleTimesUpdate, email: str = Depends(require_auth)) -> dict:
    """공고 업데이트 시간(최대 3개, "HH:MM", 00:00~23:59) 설정 UI만(2026-09-05·07 사용자 지시) —
    실제로 그 시각에 자동 실행하는 스케줄러(APScheduler)는 아직 없고, 설정값만 저장한다."""
    with engine.begin() as conn:
        try:
            found = set_schedule_times(conn, source_id, payload.schedule_times)
        except ScheduleTimesError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="소스를 찾을 수 없습니다.")
        audit.record(
            conn, actor=email, action="source.schedule_times", target_type="source", target_id=source_id,
            detail={"schedule_times": payload.schedule_times},
        )
    return {"id": source_id, "schedule_times": payload.schedule_times}


@router.post("/{source_id}/collect-now")
def collect_now_route(source_id: int, email: str = Depends(require_auth)) -> dict:
    """관리자가 스케줄과 무관하게 임의 시점에 즉시 1회 수집한다(2026-09-07 사용자 지시) —
    지금까진 python -m app.cli collect로만 가능했다. 비활성 소스·법적 등급 C는 여전히
    거부된다. 수집→중복체크→첨부분석(A1)→AI분석(A2)까지 한 번에 이어진다(같은 날 사용자
    지시) — 첨부분석·AI분석은 그 소스의 auto_extract/auto_analyze 설정을 그대로 따른다."""
    try:
        result = run_source_and_process_pending(source_id)
    except CollectionInProgressError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — 외부 API 실패(타임아웃 등)도 사용자에게 그대로 알려야 함
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"수집 중 오류가 발생했습니다: {exc}") from exc

    with engine.begin() as conn:
        audit.record(
            conn, actor=email, action="source.collect_now", target_type="source", target_id=source_id, detail=result,
        )
    return {"id": source_id, **result}


@router.get("/agencies")
def get_agencies_route(
    q: str | None = None,
    status: str | None = None,
    category: str | None = None,
    source_id: int | None = None,
    page: int = 1,
    size: int = DEFAULT_PAGE_SIZE,
    _email: str = Depends(require_auth),
) -> dict:
    with engine.connect() as conn:
        items, total = list_agencies(
            conn, q=q, status=status, category=category, source_id=source_id, page=page, size=size
        )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/agencies/categories")
def get_agency_categories_route(_email: str = Depends(require_auth)) -> list[str]:
    with engine.connect() as conn:
        return list_agency_categories(conn)


@router.get("/agencies/channels")
def get_agency_channels_route(_email: str = Depends(require_auth)) -> list[dict]:
    """공고기관(채널) 목록 — 2026-09-14, "발주기관 현황"을 공고기관 중심으로 재편하며 신설.
    채널당 소속 발주기관 수(org_count)를 붙인다. 상세(발주기관 목록)는 GET /agencies?source_id=."""
    with engine.connect() as conn:
        return list_agency_channels(conn)
