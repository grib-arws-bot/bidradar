"""report_send_log — 보고서 발송 이력(전체 현황 "보고서 발송 수" 월간 추이용)

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-12 00:00:00.000000

2026-09-12 사용자 지시 — 전체 현황 "고객 현황" 카드에 보고서 발송 수를 월간 추이로 보여줘야
하는데, newsletter_report에 "마지막 발송 시각"만 있으면 몇 번·언제 보냈는지 알 수 없어
발송할 때마다 한 행씩 남기는 로그 테이블로 잡았다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_send_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("report_id", sa.Integer, sa.ForeignKey("newsletter_report.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipients", postgresql.JSONB, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("report_send_log")
