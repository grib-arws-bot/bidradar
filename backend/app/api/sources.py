from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db import engine
from app.deps import require_auth
from app.services.agency_registry import list_agencies
from app.services.source_registry import list_sources

router = APIRouter(prefix="/api/admin/sources", tags=["sources"])


@router.get("")
def get_sources_route(_email: str = Depends(require_auth)) -> list[dict]:
    with engine.connect() as conn:
        return list_sources(conn)


@router.get("/agencies")
def get_agencies_route(
    q: str | None = None,
    status: str | None = None,
    category: str | None = None,
    _email: str = Depends(require_auth),
) -> list[dict]:
    with engine.connect() as conn:
        return list_agencies(conn, q=q, status=status, category=category)
