"""⚠️ 의도적으로 인증 없음 — 서명된 공유 링크(의사결정_로그 8·9번)로 외부 고객이 로그인 없이
보는 유일한 표면. require_auth를 절대 여기 붙이지 말 것 — 그게 이 라우터의 존재 이유다.
대신 토큰 자체가 사실상 비밀번호 역할을 한다(secrets.token_urlsafe(24), 추측 불가).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.db import engine
from app.services.interest_report import get_report_by_token

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/reports/{token}")
def get_public_report(token: str) -> dict:
    with engine.begin() as conn:
        report = get_report_by_token(conn, token)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="리포트를 찾을 수 없습니다.")
    return report
