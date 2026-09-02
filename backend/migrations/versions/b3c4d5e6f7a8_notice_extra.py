"""notice extra

Revision ID: b3c4d5e6f7a8
Revises: a7b8c9d0e1f2
Create Date: 2026-09-02 15:00:00.000000

2026-09-02 요청 — IRIS 목록 응답 16개 필드 중 notice의 명명 컬럼(title/org/open_dt/close_dt/
notice_no/url)에 안 들어가는 나머지(공모유형·소관부처·접수상태·D-day 등)를 화면 카드에
그대로 보여달라는 요청. 소스마다 부가 필드가 다르므로 전용 컬럼을 늘리지 않고(설계안 04-1
"범용 매퍼" 원칙) JSONB 하나로 받는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notice", sa.Column("extra", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("notice", "extra")
