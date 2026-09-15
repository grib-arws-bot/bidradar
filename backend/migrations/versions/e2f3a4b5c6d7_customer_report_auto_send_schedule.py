"""customer_report_auto_send_schedule — 요일·시각을 카르테시안 곱이 아닌 (요일,시각) 쌍으로

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-09-15 00:00:01.000000

2026-09-15 사용자 지시 — "월 13시, 목 14시처럼 여러 개를 지정하는 건데 지금 UI에서는
안 될 것 같다"고 뒤늦게 발견. d1e2f3a4b5c6에서 만든 report_auto_send_days(요일 배열) +
report_auto_send_times(시각 배열)는 "요일 아무거나 × 시각 아무거나"로 실행돼(app/scheduler.py
_due_customers가 두 조건을 AND로만 검사) 요일마다 다른 시각을 지정할 방법이 없었다.

기존 데이터는 카르테시안 곱으로 report_auto_send_schedule에 이관한다 — 지금까지의 실제
발송 동작(모든 요일×시각 조합에서 발송)을 그대로 보존해, 이관 시점에 사용자가 의도하지 않은
발송이 갑자기 멈추는 일이 없게 한다. 사용자는 이관 후 새 UI에서 원하는 쌍만 남기고 정리하면
된다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customer",
        sa.Column("report_auto_send_schedule", postgresql.JSONB, nullable=False, server_default="[]"),
    )
    op.execute(
        """
        UPDATE customer
        SET report_auto_send_schedule = (
            SELECT COALESCE(jsonb_agg(jsonb_build_object('day', d.day, 'time', t.time)), '[]'::jsonb)
            FROM jsonb_array_elements_text(report_auto_send_days) AS d(day)
            CROSS JOIN jsonb_array_elements_text(report_auto_send_times) AS t(time)
        )
        WHERE jsonb_array_length(report_auto_send_days) > 0
          AND jsonb_array_length(report_auto_send_times) > 0
        """
    )
    op.drop_column("customer", "report_auto_send_times")
    op.drop_column("customer", "report_auto_send_days")


def downgrade() -> None:
    op.add_column("customer", sa.Column("report_auto_send_days", postgresql.JSONB, nullable=False, server_default="[]"))
    op.add_column("customer", sa.Column("report_auto_send_times", postgresql.JSONB, nullable=False, server_default="[]"))
    op.execute(
        """
        UPDATE customer
        SET report_auto_send_days = (
                SELECT COALESCE(jsonb_agg(DISTINCT (elem->>'day')::int), '[]'::jsonb)
                FROM jsonb_array_elements(report_auto_send_schedule) AS elem
            ),
            report_auto_send_times = (
                SELECT COALESCE(jsonb_agg(DISTINCT elem->>'time'), '[]'::jsonb)
                FROM jsonb_array_elements(report_auto_send_schedule) AS elem
            )
        WHERE jsonb_array_length(report_auto_send_schedule) > 0
        """
    )
    op.drop_column("customer", "report_auto_send_schedule")
