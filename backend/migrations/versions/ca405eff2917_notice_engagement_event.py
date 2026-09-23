"""notice_engagement_event — 좋아요/클릭/상세보기 행동 데이터 로그

Revision ID: ca405eff2917
Revises: d7e8f9a0b1c2
Create Date: 2026-09-23 00:00:00.000000

2026-09-23 사용자 지시 — 향후 추천 신호로 쓰기 위해 고객의 공고별 행동(좋아요/클릭/
상세보기)을 쌓아둔다. audit_log·report_send_log와 같은 append-only 이벤트 로그
관례를 따른다. 좋아요도 별도 상태 테이블 없이 like/unlike 이벤트로 쌓고 "가장
최근 이벤트"로 현재 상태를 계산한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ca405eff2917'
down_revision: Union[str, None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notice_engagement_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notice_id", sa.Integer(), sa.ForeignKey("notice.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("newsletter_report.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("event_type IN ('like', 'unlike', 'click', 'view')", name="ck_notice_engagement_event_type"),
    )
    op.create_index(
        "ix_notice_engagement_event_lookup",
        "notice_engagement_event",
        ["customer_id", "notice_id", "event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notice_engagement_event_lookup", table_name="notice_engagement_event")
    op.drop_table("notice_engagement_event")
