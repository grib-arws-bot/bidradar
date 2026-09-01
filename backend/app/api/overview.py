from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db import engine
from app.deps import require_auth
from app.services.overview import get_overview

router = APIRouter(prefix="/api/overview", tags=["overview"])


@router.get("")
def get_overview_route(_email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        return get_overview(conn)
