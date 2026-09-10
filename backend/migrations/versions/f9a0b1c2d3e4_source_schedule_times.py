"""source schedule_times

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-09-05 00:00:00.000000

2026-09-05 요청 — "데이터 수집채널"에 채널별 공고 업데이트 시간(최대 3개, "HH:MM") 설정 UI를
추가한다. 지금은 설정값 저장만 한다 — 실제로 그 시각에 자동 실행하는 스케줄러(APScheduler,
CLAUDE.md 스택에 예약돼 있음)는 사용자 지시로 이번 범위에서 뺐다(다음 작업).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f9a0b1c2d3e4'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source",
        sa.Column("schedule_times", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("source", "schedule_times")
