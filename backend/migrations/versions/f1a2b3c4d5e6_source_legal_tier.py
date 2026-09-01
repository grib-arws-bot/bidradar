"""source legal tier

Revision ID: f1a2b3c4d5e6
Revises: 83836f1df743
Create Date: 2026-09-01 22:10:00.000000

advisory INBOX #5(2026-09-01) — 소스별 법적 등급(A/B/C)을 코드가 강제하기 위한 컬럼.
등급 없이 소스를 먼저 붙이면 나중에 등급을 도입할 때 이미 수집된 데이터가 어느 등급 규칙으로
들어왔는지 알 수 없어진다는 이유로, #2/#3(소스 등록)보다 이 마이그레이션을 먼저 적용한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = '83836f1df743'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default='A' — 기존 행(나라장터 등 전부 공공데이터포털 "제한 없음" A등급)을 채우기
    # 위한 임시값. 이후 IRIS만 B로 되돌리고 나면 이 기본값은 더 이상 필요 없어 걷어낸다.
    op.add_column("source", sa.Column("legal_tier", sa.String(length=1), nullable=False, server_default="A"))
    op.create_check_constraint("ck_source_legal_tier", "source", "legal_tier in ('A', 'B', 'C')")
    op.add_column("source", sa.Column("license_note", sa.Text(), nullable=True))
    op.add_column("source", sa.Column("license_evidence_url", sa.Text(), nullable=True))
    op.add_column("source", sa.Column("legal_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("source", sa.Column("robots_hash", sa.Text(), nullable=True))

    op.execute("UPDATE source SET legal_tier = 'B' WHERE name = 'IRIS 접수예정'")
    op.alter_column("source", "legal_tier", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_source_legal_tier", "source", type_="check")
    op.drop_column("source", "robots_hash")
    op.drop_column("source", "legal_verified_at")
    op.drop_column("source", "license_evidence_url")
    op.drop_column("source", "license_note")
    op.drop_column("source", "legal_tier")
