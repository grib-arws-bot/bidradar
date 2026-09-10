"""drop customer.price_min/price_max/regions (unused after 관심주제 필드 제거)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-05 00:00:00.000000

2026-09-05 사용자 지시 — "관심주제에서 추정가격과 지역 삭제해 줘." 이 두 조건은 매칭 점수에
가산·제외 조건으로 쓰였는데, 관리자가 실제로 쓰지 않아 제거. 편집 UI가 이미 없어졌으므로
컬럼도 완전히 드롭한다(직전 60번 결정에서 "고객 정보" 카드 쪽 중복 편집만 없앴던 것의 후속).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("customer", "regions")
    op.drop_column("customer", "price_max")
    op.drop_column("customer", "price_min")


def downgrade() -> None:
    op.add_column("customer", sa.Column("price_min", sa.Numeric(16, 0), nullable=True))
    op.add_column("customer", sa.Column("price_max", sa.Numeric(16, 0), nullable=True))
    op.add_column("customer", sa.Column("regions", postgresql.JSONB(), nullable=True))
