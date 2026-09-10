"""customer contact fields + customer_document

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
Create Date: 2026-09-05 00:00:00.000000

2026-09-05 요청 — "고객 관리" CRUD 기능. 담당자 상세(이름/직위/전화번호), 보고서 수신자
이메일 목록, 고객 보유 소개서 파일(다중, DB 바이너리 저장 — 사용자 확정: 별도 업로드
볼륨 없이 기존 db_data 볼륨에 그대로 둔다, 백엔드 이미지가 자주 재배포돼 로컬 디스크는
휘발성이라 부적합).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a0b1c2d3e4f5'
down_revision: Union[str, None] = 'f9a0b1c2d3e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("customer", sa.Column("contact_name", sa.String(100), nullable=True))
    op.add_column("customer", sa.Column("contact_title", sa.String(100), nullable=True))
    op.add_column("customer", sa.Column("contact_phone", sa.String(50), nullable=True))
    op.add_column(
        "customer",
        sa.Column("report_recipient_emails", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )

    op.create_table(
        "customer_document",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("uploaded_by", sa.String(255), nullable=False, server_default="report@grib.co.kr"),
    )


def downgrade() -> None:
    op.drop_table("customer_document")
    op.drop_column("customer", "report_recipient_emails")
    op.drop_column("customer", "contact_phone")
    op.drop_column("customer", "contact_title")
    op.drop_column("customer", "contact_name")
