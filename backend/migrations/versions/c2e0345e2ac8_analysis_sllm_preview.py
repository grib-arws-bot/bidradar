"""analysis sllm preview

사내 sLLM(A, extract-requirements) 요구사항 추출 미리보기 — analysis_requirement(A2, Haiku)와
물리적으로 분리된 테이블(의사결정_로그 178번). match.py(A3)는 이 테이블을 읽지 않는다.

Revision ID: c2e0345e2ac8
Revises: 57af4326ec1a
Create Date: 2026-09-20 02:25:16.981389

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c2e0345e2ac8'
down_revision: Union[str, None] = '57af4326ec1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_sllm_preview",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("analysis.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("sllm_job_id", sa.String(length=100)),
        sa.Column("chunks_processed", sa.Integer()),
        sa.Column("chunks_total", sa.Integer()),
        sa.Column("requirements", postgresql.JSONB()),
        sa.Column("rejected_ungrounded_count", sa.Integer()),
        sa.Column("duplicate_count", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("analysis_sllm_preview")
