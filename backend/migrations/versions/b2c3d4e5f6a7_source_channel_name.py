"""source.channel_name — 공고기관 단위 그룹핑(나라장터/IRIS 등, 2026-09-05, 공고 탐색 필터
재구성). org_name("이 소스를 운영하는 기관", 예: 나라장터 계열은 조달청)과는 다른 개념 —
사용자에게 보이는 포털/채널 브랜드명이다.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source", sa.Column("channel_name", sa.String(100), nullable=True))
    op.execute(
        """
        UPDATE source SET channel_name = CASE
            WHEN name LIKE '나라장터%' THEN '나라장터'
            WHEN name LIKE 'IRIS%' THEN 'IRIS'
            WHEN name LIKE 'K-water%' THEN 'K-water'
            WHEN name LIKE '과학기술정보통신부%' THEN '과학기술정보통신부'
            ELSE org_name
        END
        """
    )
    op.alter_column("source", "channel_name", nullable=False)


def downgrade() -> None:
    op.drop_column("source", "channel_name")
