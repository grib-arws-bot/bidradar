"""analysis_eligibility — A2 구조화 자격요건(축 5개, analysis 1건당 1행)

Revision ID: 1edbeb69cf40
Revises: fbe563e5ea30
Create Date: 2026-09-23 00:00:00.000000

2026-09-23 사용자 지시 — A2가 요약으로만 뽑던 자격요건(회사규모/연구소/벤처인증/업종/
기타 인증)을 tri-state로 구조화해 규칙 비교가 가능하게 한다. 각 축: NULL=확인불가,
[]/false=제한 없음(cite 불필요), 값 있음=제한 있음(cite 필수).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1edbeb69cf40'
down_revision: Union[str, None] = 'fbe563e5ea30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_eligibility",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_id", sa.Integer(), sa.ForeignKey("analysis.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("company_size_allowed_tiers", postgresql.JSONB, nullable=True),
        sa.Column("company_size_cite", sa.Text(), nullable=True),
        sa.Column("research_institute_required", sa.Boolean(), nullable=True),
        sa.Column("research_institute_cite", sa.Text(), nullable=True),
        sa.Column("venture_cert_required", sa.Boolean(), nullable=True),
        sa.Column("venture_cert_cite", sa.Text(), nullable=True),
        sa.Column("industry_codes_required", postgresql.JSONB, nullable=True),
        sa.Column("industry_codes_cite", sa.Text(), nullable=True),
        sa.Column("certifications_required", postgresql.JSONB, nullable=True),
        sa.Column("certifications_cite", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("analysis_eligibility")
