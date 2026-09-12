"""app_setting — 범용 key-value 앱 설정, 첫 용도는 보고서 자동삭제 보관기간

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-12 00:00:00.000000

2026-09-12 사용자 지시 — 보고서 삭제 조건(생성 후 N일)을 관리자가 설정할 수 있어야 함.
소스·고객처럼 전용 컬럼을 늘리는 대신, "다른 설정과 함께 모아 두어도 될거 같다"는 사용자
의도에 맞춰 key-value 테이블로 잡아 향후 설정이 늘어나도 스키마 변경이 필요 없게 한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("app_setting")
