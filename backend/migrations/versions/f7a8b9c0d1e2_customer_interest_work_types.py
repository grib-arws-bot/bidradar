"""customer.interest_work_types — 관심 사업유형(개발/연구/구매/구축/물품/용역/유지보수/운영/고도화)

Revision ID: f7a8b9c0d1e2
Revises: 36d41f5618f5
Create Date: 2026-09-21 00:00:00.000000

2026-09-21 사용자 지시 — 공고 추천 알고리즘 다중 신호 비교(의사결정_로그 192번)에 쓸
사업유형 선호를 고객별로 저장한다. 9개 안팎 고정값이라 interest_topic처럼 별도 카탈로그
테이블 없이 report_recipient_emails/reference_urls와 같은 방식(JSONB 문자열 배열)으로 둔다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = '36d41f5618f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customer",
        sa.Column("interest_work_types", postgresql.JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("customer", "interest_work_types")
