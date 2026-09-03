"""analysis_doc extracted text

Revision ID: c2d3e4f5a6b7
Revises: b3c4d5e6f7a8
Create Date: 2026-09-03 00:00:00.000000

S8 심층 분석 파일럿(A0+A1, 2026-09-03) — analysis_doc은 원래 추출 메타데이터(이름·크기·
sha256·추출방법·성공여부)만 담고 있었다. 원문 파일은 저장하지 않기로 했으므로(공고 URL이
항상 있어 필요하면 재다운로드 가능, 저장공간 문제 회피 — 사용자 결정) 추출된 "텍스트"만
여기 남겨야 상세 페이지에 보여줄 데이터가 남는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis_doc", sa.Column("text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_doc", "text")
