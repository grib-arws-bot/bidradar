"""customer profile summary + newsletter_report AI commentary

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-09-05 00:00:00.000000

2026-09-05 "Phase 1" 보고서 최적화 설계 확정분 — 고객 소개서를 미리 MD로 요약해 캐싱(customer
쪽)하고, 이미 규칙 기반으로 선별된 리포트 공고 목록에 "왜 의미있는지" AI 코멘트만 덧붙인다
(newsletter_report 쪽). 둘 다 관리자가 수동으로 실행(자동 실행 금지 원칙).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a0b1c2d3e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("customer", sa.Column("profile_summary_md", sa.Text(), nullable=True))
    op.add_column("customer", sa.Column("profile_summarized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("customer", sa.Column("profile_summary_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("customer", sa.Column("profile_summary_cost", sa.Numeric(10, 4), nullable=False, server_default="0"))

    op.add_column("newsletter_report", sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("newsletter_report", sa.Column("ai_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("newsletter_report", sa.Column("ai_cost_usd", sa.Numeric(10, 4), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("newsletter_report", "ai_cost_usd")
    op.drop_column("newsletter_report", "ai_tokens")
    op.drop_column("newsletter_report", "ai_generated_at")

    op.drop_column("customer", "profile_summary_cost")
    op.drop_column("customer", "profile_summary_tokens")
    op.drop_column("customer", "profile_summarized_at")
    op.drop_column("customer", "profile_summary_md")
