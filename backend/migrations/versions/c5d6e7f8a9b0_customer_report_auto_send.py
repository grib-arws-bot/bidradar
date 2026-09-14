"""customer_report_auto_send — 고객별 보고서 메일 자동발송 요일·시간 설정

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-09-14 00:00:00.000000

2026-09-14 사용자 지시 — 고객관리에 보고서 메일을 자동으로 보낼 요일·시간을 설정하는 기능을
만들고 실제로 동작해야 한다. source.schedule_times("HH:MM" 목록, 요일 개념 없음)와 달리
고객 보고서는 요일까지 지정해야 해서 필드를 둘로 나눈다 — report_auto_send_days(ISO 요일
번호 1=월~7=일의 JSONB 배열, source.schedule_times처럼 요일명 문자열 대신 숫자를 쓴 이유는
로케일에 기대지 않기 위함), report_auto_send_time("HH:MM" 문자열 하나, 고객 보고서는 여러
개 시각을 지원할 이유가 없어 소스처럼 배열로 두지 않음). 둘 다 있어야("요일 1개 이상 +
시각") 스케줄러(app/scheduler.py run_due_customer_emails)가 발송 대상으로 본다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customer",
        sa.Column("report_auto_send_days", postgresql.JSONB, nullable=False, server_default="[]"),
    )
    op.add_column(
        "customer",
        sa.Column("report_auto_send_time", sa.String(5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("customer", "report_auto_send_time")
    op.drop_column("customer", "report_auto_send_days")
