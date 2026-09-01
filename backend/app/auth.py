"""단일 공유 계정 인증 (03절 v0.3). 서버 세션 쿠키 — 세션 상태는 DB 테이블에, 쿠키는 불투명
토큰만 들고 다닌다(JWT 아님, 01절).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, insert, select
from sqlalchemy.engine import Connection

from app.config import settings
from app.models import auth_session, login_attempt
from app.security.passwords import verify_password

SESSION_TTL = timedelta(hours=12)
LOCKOUT_WINDOW = timedelta(minutes=5)
LOCKOUT_THRESHOLD = 5


class LoginError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class LockedOutError(LoginError):
    pass


def _is_locked(conn: Connection, identifier: str) -> bool:
    since = datetime.now(timezone.utc) - LOCKOUT_WINDOW
    stmt = (
        select(func.count())
        .select_from(login_attempt)
        .where(login_attempt.c.identifier == identifier)
        .where(login_attempt.c.success.is_(False))
        .where(login_attempt.c.attempted_at >= since)
    )
    return conn.execute(stmt).scalar_one() >= LOCKOUT_THRESHOLD


def authenticate(conn: Connection, email: str, password: str, client_ip: str) -> str:
    """성공하면 세션 토큰을 반환한다. 실패하면 LoginError.

    계정(email) 기준과 IP 기준을 각각 잠근다 — 단일 공유 계정이라 계정 기준만으로는
    전사가 동시에 잠길 수 있어(03절 v0.3 주석), IP 기준도 나란히 본다.
    """
    if _is_locked(conn, email) or _is_locked(conn, client_ip):
        raise LockedOutError("로그인 시도가 너무 많습니다. 5분 후 다시 시도하세요.")

    ok = bool(
        settings.admin_password_hash
        and email == settings.admin_email
        and verify_password(password, settings.admin_password_hash)
    )

    conn.execute(insert(login_attempt).values(identifier=email, success=ok))
    conn.execute(insert(login_attempt).values(identifier=client_ip, success=ok))

    if not ok:
        raise LoginError("이메일 또는 비밀번호가 올바르지 않습니다.")

    token = secrets.token_urlsafe(32)
    conn.execute(
        insert(auth_session).values(
            token=token, email=email, expires_at=datetime.now(timezone.utc) + SESSION_TTL
        )
    )
    return token


def resolve_session(conn: Connection, token: str | None) -> str | None:
    if not token:
        return None
    stmt = select(auth_session.c.email, auth_session.c.expires_at).where(auth_session.c.token == token)
    row = conn.execute(stmt).first()
    if row is None or row.expires_at < datetime.now(timezone.utc):
        return None
    return row.email


def revoke_session(conn: Connection, token: str | None) -> None:
    if not token:
        return
    conn.execute(delete(auth_session).where(auth_session.c.token == token))
