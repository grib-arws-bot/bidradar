"""범용 앱 설정(key-value, 2026-09-12) — 첫 용도는 보고서 자동 삭제 보관기간. 사용자가
"다른 설정과 함께 모아 두어도 될거 같다"고 해서, 소스·고객처럼 전용 컬럼을 늘리는 대신
나중에 설정이 더 생겨도 테이블을 안 늘려도 되는 key-value 형태로 잡는다."""

from sqlalchemy import Column, DateTime, String, Table, func
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import metadata

app_setting = Table(
    "app_setting",
    metadata,
    Column("key", String(100), primary_key=True),
    Column("value", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
