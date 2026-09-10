"""drop saved_search (unused — no creation UI ever existed)

Revision ID: d4e5f6a7b8c9
Revises: b1c2d3e4f5a6
Create Date: 2026-09-05 00:00:00.000000

2026-09-05 사용자 지시 — 고객 상세페이지 정리 중 "저장한 검색" 제거. 프론트엔드 전체에
이 데이터를 생성하는 UI가 한 번도 없었다(목록·삭제만 있었음) — 실제로 생성될 수 없는
기능이라 완전히 제거.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("saved_search")


def downgrade() -> None:
    op.create_table(
        "saved_search",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("query_params", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
