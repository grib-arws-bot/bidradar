"""notice.superseded_by_notice_id — 같은 사업이 발주계획→사전규격→입찰공고로 단계 진행될 때
이전 단계 공고를 최신 단계 공고로 무효화 표시

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-06 00:00:00.000000

2026-09-06 사용자 지시 — "동일 발주기관·동일 사업명이 발주계획/사전규격/입찰공고에 중복
등장하는 건 하나의 사업이 단계별로 진행된 것 — 가장 최근에 공고된 걸 기준으로 하고 이전
것들은 무효화해야 한다." 하드 삭제 대신 포인터만 남긴다(감사·추적 가능성 유지, 다른
레지스트리의 "비활성화만" 원칙과 같은 이유).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notice",
        sa.Column("superseded_by_notice_id", sa.Integer(), sa.ForeignKey("notice.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_notice_superseded_by_notice_id", "notice", ["superseded_by_notice_id"])


def downgrade() -> None:
    op.drop_index("ix_notice_superseded_by_notice_id", table_name="notice")
    op.drop_column("notice", "superseded_by_notice_id")
