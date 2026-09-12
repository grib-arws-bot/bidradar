from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db import engine
from app.deps import require_auth
from app.services.overview import get_customer_overview, get_notice_overview, get_system_overview

router = APIRouter(prefix="/api/overview", tags=["overview"])


# 2026-09-12 재설계 — 카드 3개(고객 현황/시스템 현황/공고 데이터)로 나눠 각자 API도 분리했다.
# 서버 자원(system_resources.py)이 CPU 측정에 0.3초 정도 걸려 나머지 카드까지 기다리게 하면
# 안 되므로, 하나로 묶지 않고 프런트가 3번 병렬로 불러오게 한다.
@router.get("/customers")
def get_customer_overview_route(_email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        return get_customer_overview(conn)


@router.get("/system")
def get_system_overview_route(_email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        return get_system_overview(conn)


@router.get("/notices")
def get_notice_overview_route(_email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        return get_notice_overview(conn)
