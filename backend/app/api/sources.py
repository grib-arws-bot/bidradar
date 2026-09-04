from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db import engine
from app.deps import require_auth
from app.services import audit
from app.services.agency_registry import list_agencies
from app.services.source_registry import list_sources, set_auto_extract

router = APIRouter(prefix="/api/admin/sources", tags=["sources"])


class AutoExtractUpdate(BaseModel):
    auto_extract: bool


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


@router.get("/agencies")
def get_agencies_route(
    q: str | None = None,
    status: str | None = None,
    category: str | None = None,
    _email: str = Depends(require_auth),
) -> list[dict]:
    with engine.connect() as conn:
        return list_agencies(conn, q=q, status=status, category=category)
