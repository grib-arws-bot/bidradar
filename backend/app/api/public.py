"""⚠️ 의도적으로 인증 없음 — 서명된 공유 링크(의사결정_로그 8·9번)로 외부 고객이 로그인 없이
보는 유일한 표면. require_auth를 절대 여기 붙이지 말 것 — 그게 이 라우터의 존재 이유다.
대신 토큰 자체가 사실상 비밀번호 역할을 한다(secrets.token_urlsafe(24), 추측 불가).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.db import engine
from app.services.analysis.structure_query import get_requirements
from app.services.analysis_pilot import get_latest_extraction
from app.services.interest_report import get_report_by_token
from app.services.notice_eligibility import get_eligibility_verdict
from app.services.notice_engagement import record_click, record_view, set_like
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
    report = _authorize_notice_in_report(token, notice_id)
    with engine.connect() as conn:
        notice_info = get_public_notice_summary(conn, notice_id, customer_id=report["customer_id"])
    if notice_info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="공고를 찾을 수 없습니다.")
    return notice_info


# 공고탐색(관리자 화면)과 같은 상세 분석 내용을 리포트에도 그대로 보여주기 위함(2026-09-12
# 사용자 지시 — "공고탐색의 공고 상세페이지와 내용이 모두 들어가게"). get_requirements·
# get_latest_extraction은 인증 로직이 없는 순수 조회 함수라(app/api/notices.py도 이미 이렇게
# 씀) 토큰 검증(_authorize_notice_in_report)만 이 라우터 방식대로 앞에 걸면 된다. A2
# requirement에는 자사 제품 충족판정 같은 내부 판정 필드 자체가 없어(app/services/
# analysis/structure.py, S8 원칙 1 — LLM은 판정하지 않음) 그대로 노출해도 안전하다.
@router.get("/reports/{token}/notices/{notice_id}/requirements")
def get_public_notice_requirements(token: str, notice_id: int) -> dict | None:
    _authorize_notice_in_report(token, notice_id)
    with engine.connect() as conn:
        return get_requirements(conn, notice_id)


@router.get("/reports/{token}/notices/{notice_id}/extract")
def get_public_notice_extraction(token: str, notice_id: int) -> dict | None:
    _authorize_notice_in_report(token, notice_id)
    with engine.connect() as conn:
        return get_latest_extraction(conn, notice_id)


@router.get("/reports/{token}/notices/{notice_id}/eligibility")
def get_public_notice_eligibility(token: str, notice_id: int) -> dict | None:
    """입찰 자격요건 검증(2026-09-23) — 토큰에서 이미 고객이 정해지므로 별도 선택 없이
    자동 조회된다. 점수와 무관한 별도 판정이라 다른 공개 조회 함수들과 같은 방식으로
    노출해도 안전하다."""
    report = _authorize_notice_in_report(token, notice_id)
    with engine.connect() as conn:
        return get_eligibility_verdict(conn, report["customer_id"], notice_id)


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


# 행동 데이터 수집(2026-09-23, 향후 추천 신호로 쓰기 위해 쌓아둠) — 클릭/상세보기는 실패해도
# 화면 동작에 영향 주면 안 되는 부가 신호라 204만 반환한다. 좋아요는 토글이 아니라 원하는
# 상태를 명시하는 PUT — 중복 클릭·네트워크 재시도에도 안전(토글이면 의도와 반대로 뒤집힐
# 위험이 있음).
@router.post("/reports/{token}/notices/{notice_id}/click", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def post_public_notice_click(token: str, notice_id: int) -> None:
    report = _authorize_notice_in_report(token, notice_id)
    record_click(report["customer_id"], notice_id, report["id"])


@router.post("/reports/{token}/notices/{notice_id}/view", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def post_public_notice_view(token: str, notice_id: int) -> None:
    report = _authorize_notice_in_report(token, notice_id)
    record_view(report["customer_id"], notice_id, report["id"])


class LikeRequest(BaseModel):
    liked: bool


class LikeResponse(BaseModel):
    liked: bool


@router.put("/reports/{token}/notices/{notice_id}/like", response_model=LikeResponse)
def put_public_notice_like(token: str, notice_id: int, body: LikeRequest) -> LikeResponse:
    report = _authorize_notice_in_report(token, notice_id)
    liked = set_like(report["customer_id"], notice_id, report["id"], body.liked)
    return LikeResponse(liked=liked)
