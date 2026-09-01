"""source homepage url

Revision ID: 5db28308fbcd
Revises: ed135ab01d84
Create Date: 2026-09-01 19:28:43.773262

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5db28308fbcd'
down_revision: Union[str, None] = 'ed135ab01d84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source", sa.Column("homepage_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("source", "homepage_url")
