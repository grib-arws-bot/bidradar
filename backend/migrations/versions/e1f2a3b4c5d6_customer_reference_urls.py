"""customer.reference_urls — AI 고객 분석에 함께 넣을 참고 URL 목록

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-11 00:00:00.000000

2026-09-11 사용자 지시 — "소개서 파일" 섹션을 "AI 고객 분석"으로 바꾸고, 파일 업로드 외에
URL도 여러 개 입력해 요약 분석 시 함께 넣도록. report_recipient_emails와 같은 방식
(JSONB 문자열 배열)으로 저장한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customer",
        sa.Column("reference_urls", postgresql.JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("customer", "reference_urls")
