"""서버 세션 쿠키용 테이블 (03절 — JWT 아님, DB 테이블 기반, Redis 금지 원칙 그대로 적용).

08절 데이터모델에는 없는 인증 인프라용 테이블이라 별도 모듈로 둔다.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Table, func

from app.models.base import metadata

auth_session = Table(
    "auth_session",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("token", String(64), nullable=False, unique=True),
    Column("email", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

# 로그인 5회 실패 시 5분 잠금(03절) — 계정 식별자·IP 둘 다 이 테이블에 같은 방식으로 기록해서
# 전사가 계정 하나를 공유해도(단일 로그인, 03절 v0.3) IP 기준으로도 잠금이 걸리게 한다.
login_attempt = Table(
    "login_attempt",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("identifier", String(255), nullable=False),  # email 또는 client IP
    Column("success", Boolean, nullable=False),
    Column("attempted_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
