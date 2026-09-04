"""analysis.summary — S8 A2 사업개요/사업내용/평가기준 요약(2026-09-05, 공고 상세페이지 종합)

Revision ID: a1b2c3d4e5f6
Revises: e7f8a9b0c1d2
Create Date: 2026-09-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis", sa.Column("summary", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis", "summary")
