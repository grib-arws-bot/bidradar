"""⚠️ 의도적으로 인증 없음 — 서명된 공유 링크(의사결정_로그 8·9번)로 외부 고객이 로그인 없이
보는 유일한 표면. require_auth를 절대 여기 붙이지 말 것 — 그게 이 라우터의 존재 이유다.
대신 토큰 자체가 사실상 비밀번호 역할을 한다(secrets.token_urlsafe(24), 추측 불가).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.db import engine
from app.services.interest_report import get_report_by_token
from app.services.notice_strategy import (
    LLMNotConfiguredError,
    NoticeNotFoundError,
    get_or_generate_strategy,
    get_public_notice_summary,
)

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/reports/{token}")
def get_public_report(token: str) -> dict:
    with engine.begin() as conn:
        report = get_report_by_token(conn, token)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="리포트를 찾을 수 없습니다.")
    return report


def _authorize_notice_in_report(token: str, notice_id: int) -> dict:
    """토큰이 실제로 이 공고를 담은 리포트의 것인지 확인 — 토큰 하나로 그 리포트에 스냅샷된
    공고만 볼 수 있어야 한다(다른 공고 id를 아무거나 넣어 조회하는 걸 막음)."""
    with engine.connect() as conn:
        report = get_report_by_token(conn, token, record_view=False)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="리포트를 찾을 수 없습니다.")
    if not any(n["id"] == notice_id for n in report["notices"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="이 리포트에 포함되지 않은 공고입니다.")
    return report


@router.get("/reports/{token}/notices/{notice_id}")
def get_public_notice(token: str, notice_id: int) -> dict:
    _authorize_notice_in_report(token, notice_id)
    with engine.connect() as conn:
        notice_info = get_public_notice_summary(conn, notice_id)
    if notice_info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="공고를 찾을 수 없습니다.")
    return notice_info


class StrategyResponse(BaseModel):
    status: str
    strategy_md: str | None = None
    model: str | None = None
    cost_usd: float | None = None


@router.post("/reports/{token}/notices/{notice_id}/strategy", response_model=StrategyResponse)
def post_public_notice_strategy(token: str, notice_id: int) -> StrategyResponse:
    """고객이 "사업 추진 전략"을 열 때(처음 열 때만 실제로 생성) — 몇 번을 다시 눌러도
    (customer_id, notice_id) 유니크 제약으로 실제 LLM 호출은 한 번만 일어난다."""
    report = _authorize_notice_in_report(token, notice_id)
    try:
        result = get_or_generate_strategy(report["customer_id"], notice_id)
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    except NoticeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — 고객에게는 "실패했습니다"만, 원인은 서버 로그/DB에 남음
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="전략 생성에 실패했습니다. 잠시 후 다시 시도해주세요.") from exc
    return StrategyResponse(**result)
