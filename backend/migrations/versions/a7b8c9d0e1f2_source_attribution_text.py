"""source attribution text

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-09-01 22:30:00.000000

advisory INBOX #7(2026-09-01) — 공공데이터포털 정책상 제0유형 외 전 유형은 출처표시 의무가
있다. 사람이 매번 기억해서 붙이는 게 아니라 템플릿 레벨에서 자동으로 붙게 하기 위한 컬럼.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source", sa.Column("attribution_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("source", "attribution_text")
