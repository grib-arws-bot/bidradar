"""customer.interest_price_min — 관심 공고 추천에 적용할 금액 하한

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-07 00:00:00.000000

2026-09-07 사용자 지시 — "고객관리의 관심주제 선택화면에서 금액 하한을 정하도록 하자.
추천 공고에서는 이 하한 금액 이상인 것만 추천되도록." 2026-09-05에 관심주제 화면에서
추정가격·지역 조건을 뺐었는데(그때는 안 쓰였음), 이번엔 하한선 하나만 다시 들여온다
(→ 05번 결정에서 일부 변경됨, 의사결정_로그 참고).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("customer", sa.Column("interest_price_min", sa.Numeric(16, 0), nullable=True))


def downgrade() -> None:
    op.drop_column("customer", "interest_price_min")
