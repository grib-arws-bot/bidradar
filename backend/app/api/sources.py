from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db import engine
from app.deps import require_auth
from app.services.source_registry import list_sources

router = APIRouter(prefix="/api/admin/sources", tags=["sources"])


@router.get("")
def get_sources_route(_email: str = Depends(require_auth)) -> list[dict]:
    with engine.connect() as conn:
        return list_sources(conn)
