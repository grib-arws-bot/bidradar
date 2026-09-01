"""org abbr notice_url source_id

Revision ID: 3ec80954c7b9
Revises: 5db28308fbcd
Create Date: 2026-09-01 20:25:59.117541

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ec80954c7b9'
down_revision: Union[str, None] = '5db28308fbcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("org", sa.Column("abbr", sa.String(length=30), nullable=True))
    op.add_column("org", sa.Column("notice_url", sa.Text(), nullable=True))
    op.add_column("org", sa.Column("source_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_org_source_id", "org", "source", ["source_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_org_source_id", "org", type_="foreignkey")
    op.drop_column("org", "source_id")
    op.drop_column("org", "notice_url")
    op.drop_column("org", "abbr")
