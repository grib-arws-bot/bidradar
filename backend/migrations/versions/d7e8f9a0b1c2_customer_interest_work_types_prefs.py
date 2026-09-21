"""customer.interest_work_types — 배열(선택 목록) -> 객체({사업유형: positive|negative})

Revision ID: d7e8f9a0b1c2
Revises: f7a8b9c0d1e2
Create Date: 2026-09-21 00:00:00.000000

2026-09-21 사용자 후속 지시 — 사업유형이 단순 "선택했다/안 했다"가 아니라 "선호(+)/중립/
비선호(-)" 3단계여야 한다(감리·구매처럼 오히려 감점해야 할 유형이 있음). 컬럼을 새로
만들 필요는 없다(이미 JSONB) — 담기는 값의 모양만 배열에서 객체로 바뀐다. 이 컬럼은
같은 날 처음 만들어져 아직 실사용이 없었을 것으로 보이지만(기본값 '[]'만 있는 상태),
방어적으로 배열 모양인 기존 행을 전부 빈 객체로 백필한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE customer ALTER COLUMN interest_work_types SET DEFAULT '{}'::jsonb")
    op.execute(
        "UPDATE customer SET interest_work_types = '{}'::jsonb "
        "WHERE jsonb_typeof(interest_work_types) = 'array'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE customer SET interest_work_types = '[]'::jsonb "
        "WHERE jsonb_typeof(interest_work_types) = 'object'"
    )
    op.execute("ALTER TABLE customer ALTER COLUMN interest_work_types SET DEFAULT '[]'::jsonb")
