"""customer_report_auto_send_times — 보고서 메일 자동발송 시각을 복수 지정 가능하도록 확장

Revision ID: d1e2f3a4b5c6
Revises: c5d6e7f8a9b0
Create Date: 2026-09-15 00:00:00.000000

2026-09-15 사용자 지시 — "메일 발송 시점은 다수개를 지정할 수 있어야 한다." c5d6e7f8a9b0에서
"고객 보고서는 여러 개 시각을 지원할 이유가 없다"고 판단해 단일 문자열로 뒀던 걸 뒤집는다 —
source.schedule_times와 완전히 같은 모양(JSONB 배열, 최대 3개 "HH:MM")으로 통일한다.
기존 report_auto_send_time에 값이 있던 행은 그 값을 1개짜리 배열로 이관한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customer",
        sa.Column("report_auto_send_times", postgresql.JSONB, nullable=False, server_default="[]"),
    )
    op.execute(
        "UPDATE customer SET report_auto_send_times = jsonb_build_array(report_auto_send_time) "
        "WHERE report_auto_send_time IS NOT NULL"
    )
    op.drop_column("customer", "report_auto_send_time")


def downgrade() -> None:
    op.add_column("customer", sa.Column("report_auto_send_time", sa.String(5), nullable=True))
    op.execute(
        "UPDATE customer SET report_auto_send_time = report_auto_send_times->>0 "
        "WHERE jsonb_array_length(report_auto_send_times) > 0"
    )
    op.drop_column("customer", "report_auto_send_times")
