"""analysis_requirement.task_ref — 성능 요구사항을 과제(content_items) 단위로 묶어 보여주기
위한 참조 컬럼(2026-09-05, "성능 요구사항은 과제 개요의 각 과제 하위에" 요청). 판정 로직
(match.py)엔 영향 없음 — 화면 표시용 그룹핑 키.

Revision ID: d3e4f5a6b7c8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis_requirement", sa.Column("task_ref", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_requirement", "task_ref")
