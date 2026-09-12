"""notice_title_exclude_word — 공고 탐색 제목 제외 키워드 그룹(관리 편의상 그룹 1개만 존재)

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-13 00:00:00.000000

2026-09-13 사용자 지시 — 공고 탐색 화면에서 "감리/모집/고도화/유지보수"처럼 제목에 들어있으면
보고 싶지 않은 단어를 저장해뒀다가 화면에서 켜고 끌 수 있어야 한다. keyword_rule(L2 관심주제
채점용)과는 완전히 별개 — 이건 수집·채점에 관여하지 않고 순수 조회 시점 필터다. 관리 편의를
위해 그룹을 여러 개 두지 않고 단어 목록 하나로만 관리한다(그룹 테이블 자체가 불필요).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notice_title_exclude_word",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("term", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("notice_title_exclude_word")
