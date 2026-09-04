"""source auto_extract

Revision ID: e7f8a9b0c1d2
Revises: c2d3e4f5a6b7
Create Date: 2026-09-05 00:00:00.000000

2026-09-05 요청 — S8 심층 분석 파일럿(첨부문서 다운로드+텍스트 추출)을 공고 수집과 동시에
자동으로 실행할지 소스별로 관리자가 켜고 끌 수 있게 한다. CLAUDE.md S8 원칙 3
("자동 실행 금지 — 사용자가 지정할 때만 실행한다")과 충돌하지 않는다 — 시스템이 알아서
결정하는 게 아니라 관리자가 소스 등록 시 미리 정해두는 명시적 설정이기 때문. 기본값 False
(나라장터처럼 물량이 많은 소스가 실수로 켜져 있지 않도록) — IRIS류만 시드에서 True로 켠다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source", sa.Column("auto_extract", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("source", "auto_extract")
