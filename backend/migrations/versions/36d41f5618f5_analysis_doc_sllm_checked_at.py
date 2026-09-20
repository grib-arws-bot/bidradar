"""analysis doc sllm checked at

Revision ID: 36d41f5618f5
Revises: c2e0345e2ac8
Create Date: 2026-09-20 18:13:40.748237

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36d41f5618f5'
down_revision: Union[str, None] = 'c2e0345e2ac8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis_doc", sa.Column("sllm_checked_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("analysis_doc", "sllm_checked_at")
