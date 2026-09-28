"""customer.interest_min_lead_days — 마감임박 제외 기준(일)

Revision ID: 5965017b4520
Revises: 1edbeb69cf40
Create Date: 2026-09-28 00:00:00.000000

2026-09-28 사용자 지시 — 마감까지 D-7 이내로 남은 공고는 너무 촉박해 제외한다. 이 값을
고객마다 다르게 설정할 수 있게 한다(NULL이면 전역 기본값 7일 적용).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5965017b4520'
down_revision: Union[str, None] = '1edbeb69cf40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("customer", sa.Column("interest_min_lead_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("customer", "interest_min_lead_days")
