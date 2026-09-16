"""notice.embedding — pgvector 확장 + 코사인 유사도 매칭용 임베딩 컬럼

Revision ID: 9938acb2ba9d
Revises: f4a5b6c7d8e9
Create Date: 2026-09-16 00:00:00.000000

2026-09-16 사용자 지시 — 관심공고 추천이 규칙(키워드) 매칭 하나뿐이라 "관계없는 것들이
섞인다"는 지적에, 외부 사례 조사 결과를 바탕으로 규칙 매칭과 나란히 비교해볼 코사인
유사도 매칭을 추가한다(의사결정_로그 157/158번 후속). notice.embedding에 BAAI/bge-m3
(자체 호스팅, 1024차원) 벡터를 저장 — 기존 공고는 배치(app/services/embeddings.py,
run_pending_embeddings)가 서서히 채운다. HNSW 인덱스로 코사인 거리 검색을 빠르게 한다.

OpenAI API로 시작하려 했으나 새 벤더 키 발급 마찰이 있어 자체 호스팅으로 전환(같은 날,
사용자 지시) — bge-m3가 다국어(한국어 포함) 검색 벤치마크에서 OpenAI text-embedding-3-small
을 앞서는 경우가 많다는 조사 결과도 근거. 벡터 차원이 1536→1024로 바뀌어(OpenAI→bge-m3)
이 마이그레이션을 직접 고쳤다 — 이 시점까지 어디에도 배포된 적 없어(로컬 개발 DB에만
적용) 새 마이그레이션을 얹지 않고 그대로 수정.

db 이미지를 postgres:16.4-bookworm → pgvector/pgvector:0.8.0-pg16-bookworm으로 교체했다
(infra/docker-compose.yml, 같은 Postgres 16 + bookworm 베이스에 확장만 미리 빌드된
드롭인이라 데이터 포맷 변경 없음).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '9938acb2ba9d'
down_revision: Union[str, None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1024  # BAAI/bge-m3 dense 출력 차원


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("notice", sa.Column("embedding", Vector(EMBEDDING_DIM)))
    op.execute(
        "CREATE INDEX ix_notice_embedding_hnsw ON notice USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notice_embedding_hnsw")
    op.drop_column("notice", "embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
