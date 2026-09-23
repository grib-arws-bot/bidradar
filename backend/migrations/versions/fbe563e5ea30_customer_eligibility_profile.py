"""customer 자격 프로필 컬럼 — 입찰 자격요건 검증

Revision ID: fbe563e5ea30
Revises: ca405eff2917
Create Date: 2026-09-23 00:00:00.000000

2026-09-23 사용자 지시 — 기업규모/연구소 보유/벤처인증/업종/기타 인증을 고객사 자신의
프로필로 저장해 공고의 자격요건과 대조한다(docs/구현스펙.md 07절 "향후 과제"). NULL은
"미입력"이지 "미보유"가 아니다 — 비교기는 NULL을 항상 "확인 필요"로 처리한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fbe563e5ea30'
down_revision: Union[str, None] = 'ca405eff2917'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("customer", sa.Column("eligibility_company_size_tier", sa.String(10), nullable=True))
    op.add_column("customer", sa.Column("eligibility_has_research_institute", sa.Boolean(), nullable=True))
    op.add_column("customer", sa.Column("eligibility_venture_cert", sa.Boolean(), nullable=True))
    op.add_column(
        "customer",
        sa.Column("eligibility_industry_codes", postgresql.JSONB, nullable=False, server_default="[]"),
    )
    op.add_column(
        "customer",
        sa.Column("eligibility_certifications", postgresql.JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("customer", "eligibility_certifications")
    op.drop_column("customer", "eligibility_industry_codes")
    op.drop_column("customer", "eligibility_venture_cert")
    op.drop_column("customer", "eligibility_has_research_institute")
    op.drop_column("customer", "eligibility_company_size_tier")
