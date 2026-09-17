"""notice embedding with attachment text

Revision ID: 2aa119eed8de
Revises: 7a8834121d17
Create Date: 2026-09-17 21:24:15.362547

2026-09-17 — 사용자가 매칭 비교 화면에서 규칙 매칭과 코사인(제목만) 매칭의 일치율이
20건 중 2~3건으로 너무 낮다고 지적, 원인을 보니 규칙 매칭은 이미 A1 첨부 전체 추출
텍스트로 재채점(rule_ver=2, notice_topic_scoring.py)하는데 코사인은 제목·발주기관·
지역·단계만 봐서 정보량 자체가 다른 게 컸다. A1 텍스트를 반영한 임베딩을 추가해 총
3방식(규칙/코사인-제목/코사인-첨부)을 비교하기로 함 — 기존 embedding 컬럼을 덮어쓰면
"제목만" 결과가 사라져 비교가 안 되므로, 별도 컬럼으로 둔다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '2aa119eed8de'
down_revision: Union[str, None] = '7a8834121d17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1024  # BAAI/bge-m3 dense 출력 차원


def upgrade() -> None:
    op.add_column("notice", sa.Column("embedding_a1", Vector(EMBEDDING_DIM)))
    op.add_column("notice", sa.Column("embedded_a1_at", sa.DateTime(timezone=True)))
    op.execute(
        "CREATE INDEX ix_notice_embedding_a1_hnsw ON notice USING hnsw (embedding_a1 vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notice_embedding_a1_hnsw")
    op.drop_column("notice", "embedded_a1_at")
    op.drop_column("notice", "embedding_a1")
