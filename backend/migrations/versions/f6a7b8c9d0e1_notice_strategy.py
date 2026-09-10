"""notice_strategy — per (customer, notice) AI 사업 추진 전략 캐시

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-05 00:00:00.000000

2026-09-05 사용자 지시 — 공개 리포트에서 고객이 공고를 클릭해 들어가면 "AI 분석을 통한
사업 추진 전략" 페이지로 갈 수 있어야 하고, 미리 만들어두지 않고 고객이 눌렀을 때만
생성하되 여러 번 눌러도 여러 번 분석하면 안 된다. (customer_id, notice_id) unique
제약으로 INSERT ... ON CONFLICT DO NOTHING을 원자적 "선점" 수단으로 쓴다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notice_strategy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notice_id", sa.Integer(), sa.ForeignKey("notice.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("strategy_md", sa.Text(), nullable=True),
        sa.Column("model", sa.String(50), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("customer_id", "notice_id", name="uq_notice_strategy_customer_notice"),
    )


def downgrade() -> None:
    op.drop_table("notice_strategy")
