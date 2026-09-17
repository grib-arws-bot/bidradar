from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db import engine
from app.deps import require_auth
from app.services.overview import (
    get_ai_processing_overview,
    get_customer_overview,
    get_notice_overview,
    get_ops_overview,
    get_system_overview,
)

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


# 2026-09-17 — "공고 데이터" 카드에 그래프 2개 추가(일별 AI 처리 현황·일별 운영 현황). 위와
# 같은 이유로 별도 엔드포인트로 분리해 병렬 로딩한다.
@router.get("/ai-processing")
def get_ai_processing_overview_route(_email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        return get_ai_processing_overview(conn)


@router.get("/ops")
def get_ops_overview_route(_email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        return get_ops_overview(conn)
