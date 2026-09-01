"""라우터는 얇게 — 실제 로직은 app/auth.py(CLAUDE.md 코드 규칙)."""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.auth import LockedOutError, LoginError, authenticate, create_dev_session, revoke_session
from app.config import settings
from app.db import engine
from app.deps import SESSION_COOKIE_NAME, require_auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class MeResponse(BaseModel):
    email: str


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        # X-Forwarded-Proto로 판단하지 않고 환경변수로 고정 — ARWS에서 겪은 Secure 플래그 사고 재현 방지
        secure=not settings.is_dev,
        max_age=12 * 3600,
        path="/",
    )


@router.post("/login", response_model=MeResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> MeResponse:
    # 실패 시도 기록은 인증 실패 여부와 무관하게 항상 커밋돼야 하므로, with 블록 밖에서
    # HTTPException을 던진다 — 안에서 던지면 engine.begin()이 attempt insert까지 롤백해버려서
    # login_attempt가 하나도 안 쌓이고 잠금이 영원히 안 걸리는 버그가 생긴다.
    token: str | None = None
    login_error: LoginError | None = None
    with engine.begin() as conn:
        try:
            token = authenticate(conn, payload.email, payload.password, _client_ip(request))
        except LoginError as exc:
            login_error = exc

    if login_error is not None:
        status_code = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if isinstance(login_error, LockedOutError)
            else status.HTTP_401_UNAUTHORIZED
        )
        raise HTTPException(status_code=status_code, detail=login_error.message)

    assert token is not None
    _set_session_cookie(response, token)
    return MeResponse(email=payload.email)


@router.post("/dev-autologin", response_model=MeResponse)
def dev_autologin(response: Response) -> MeResponse:
    """로컬 개발 전용 자동로그인 — 비밀번호를 매번 입력하지 않아도 되도록.

    settings.is_dev(=ENVIRONMENT != "production")가 아니면 404 — 실서버 배포 시
    .env의 ENVIRONMENT=production 하나만 지키면 이 경로 자체가 존재하지 않게 된다.
    프론트 어디에도 실제 비밀번호를 심지 않고, 여기서 비밀번호 검증 자체를 건너뛴다.
    """
    if not settings.is_dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    with engine.begin() as conn:
        token = create_dev_session(conn)
    _set_session_cookie(response, token)
    return MeResponse(email=settings.admin_email)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, bidradar_session: str | None = Cookie(default=None)) -> None:
    with engine.begin() as conn:
        revoke_session(conn, bidradar_session)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=MeResponse)
def me(email: str = Depends(require_auth)) -> MeResponse:
    return MeResponse(email=email)
