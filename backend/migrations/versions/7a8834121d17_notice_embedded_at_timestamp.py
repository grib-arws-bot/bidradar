"""notice embedded_at timestamp

Revision ID: 7a8834121d17
Revises: 9938acb2ba9d
Create Date: 2026-09-17 19:34:39.409787

2026-09-17 — 전체 현황 "누적 데이터" 그래프에 "임베딩 완료 누적" 계열을 추가하려는데,
notice.embedding 자체엔 언제 채워졌는지 시각 정보가 없어 과거 추이를 재구성할 수 없었다.
이 컬럼을 별도로 둬야 오늘 이후부터 정확한 일별 누적 추이를 그릴 수 있다(과거분은 어차피
오늘 배치로 한꺼번에 채워지는 중이라 소급 적용할 데이터 자체가 없음 — NULL로 둬도 무방).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a8834121d17'
down_revision: Union[str, None] = '9938acb2ba9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notice", sa.Column("embedded_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("notice", "embedded_at")
