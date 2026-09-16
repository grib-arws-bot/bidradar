"""customer_report_auto_send_schedule의 day를 문자열에서 정수로 백필

Revision ID: f4a5b6c7d8e9
Revises: e2f3a4b5c6d7
Create Date: 2026-09-16 00:00:00.000000

2026-09-16 발견 — e2f3a4b5c6d7이 jsonb_array_elements_text()로 기존 요일 값을 옮기며 day를
JSON 문자열("3")로 저장했다. app/scheduler.py._due_customers()는 정수 isoweekday()와
`==`로 비교하므로 이 재설계가 나온 2026-09-15부터 오늘까지 자동발송이 단 한 건도 실행되지
못했다(사용자는 "지금 발송" 수동 클릭으로만 확인했음 — 자동 스케줄은 침묵 실패).
day를 정수로 백필한다.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE customer
        SET report_auto_send_schedule = (
            SELECT COALESCE(
                jsonb_agg(jsonb_build_object('day', (elem->>'day')::int, 'time', elem->>'time')),
                '[]'::jsonb
            )
            FROM jsonb_array_elements(report_auto_send_schedule) AS elem
        )
        WHERE jsonb_array_length(report_auto_send_schedule) > 0
        """
    )


def downgrade() -> None:
    # day를 문자열로 되돌리는 건 버그를 재현하는 것뿐이라 downgrade에서는 그대로 둔다.
    pass
