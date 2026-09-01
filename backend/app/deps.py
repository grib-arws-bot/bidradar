from fastapi import Cookie, HTTPException, status

from app.auth import resolve_session
from app.db import engine

SESSION_COOKIE_NAME = "bidradar_session"


def require_auth(bidradar_session: str | None = Cookie(default=None)) -> str:
    """로그인 여부만 확인하는 단일 의존성 — 역할 구분 없음(03절 v0.3, require_admin 폐기)."""
    with engine.connect() as conn:
        email = resolve_session(conn, bidradar_session)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다. 세션이 없거나 만료됐습니다.",
        )
    return email
