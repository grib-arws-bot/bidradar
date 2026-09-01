"""notice biz_type work_type

Revision ID: 83836f1df743
Revises: 3ec80954c7b9
Create Date: 2026-09-01 21:02:14.416627

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '83836f1df743'
down_revision: Union[str, None] = '3ec80954c7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notice", sa.Column("biz_type", sa.String(length=20), nullable=True))
    op.add_column("notice", sa.Column("work_type", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("notice", "work_type")
    op.drop_column("notice", "biz_type")
