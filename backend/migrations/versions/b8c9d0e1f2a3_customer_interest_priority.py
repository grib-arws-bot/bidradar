"""customer_interest.priority — 관심주제별 3단계 우선순위(high/normal/low)

Revision ID: b8c9d0e1f2a3
Revises: f6a7b8c9d0e1
Create Date: 2026-09-05 00:00:00.000000

2026-09-05 사용자 지시 — 지금까지는 고객이 선택한 관심주제가 전부 동일한 가중치(+30)로만
매칭 점수에 반영돼, 회사 핵심 사업(예: 산업안전)과 부차적 관심사(예: 농수산)가 똑같이
취급되는 문제가 있었다("스마트 공원 공고가 산업안전 주제인데 왜 추천 순위가 안 높나"
사용자 지적). 3단계 우선순위를 둬서 핵심 주제일수록 매칭 점수가 높게 만든다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("customer_interest", sa.Column("priority", sa.String(10), nullable=False, server_default="normal"))


def downgrade() -> None:
    op.drop_column("customer_interest", "priority")
