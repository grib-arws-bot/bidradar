"""source auto_analyze

Revision ID: e8f9a0b1c2d3
Revises: d3e4f5a6b7c8
Create Date: 2026-09-05 00:00:00.000000

2026-09-05 요청 — A2(요구사양 구조화, LLM 호출·비용 발생)를 auto_extract 성공 직후 자동으로
이어서 실행할지 소스별로 관리자가 켜고 끌 수 있게 한다. auto_extract 컬럼(e7f8a9b0c1d2)과
같은 논리로 CLAUDE.md S8 원칙 3과 충돌하지 않는다고 판단(사용자 확정) — 관리자가 이 화면에서
미리 정해두는 명시적 설정이라 "시스템이 알아서 트는" 자동 실행이 아니다. 항상 Haiku로만
실행하고(모델 선택 자동화는 안 함), 기본값 False.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source", sa.Column("auto_analyze", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("source", "auto_analyze")
