"""notice sllm topic match

Revision ID: 57af4326ec1a
Revises: 2aa119eed8de
Create Date: 2026-09-20 01:56:50.612448

2026-09-20 — 관심주제 시맨틱 필터(sLLM B, classify-topic, 의사결정_로그 175/177번). 키워드
규칙(L2)이 놓치는 표현 변형("자동화 설비"가 "로봇" 키워드를 안 담는 경우 등)을 sLLM으로
보조 확인한다. `notice_score.l3_conf`는 설계안 05절상 "L3(LLM 도메인 판정) 확신도"로 이미
용도가 정해져 있어(산업안전/스마트교육/무관 판정용, 아직 미구현) 재사용하지 않고 별도
컬럼(sllm_confidence)을 둔다 — 나중에 L3가 실제 구현될 때 의미가 섞이면 안 된다.

notice.sllm_topic_checked_at은 embedded_at/embedded_a1_at과 동일한 패턴 — 이 공고의
제목을 sLLM으로 이미 확인했는지 추적해 배치가 매번 전체를 다시 훑지 않게 한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57af4326ec1a'
down_revision: Union[str, None] = '2aa119eed8de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notice", sa.Column("sllm_topic_checked_at", sa.DateTime(timezone=True)))
    op.add_column("notice_score", sa.Column("sllm_confidence", sa.Numeric(4, 3)))


def downgrade() -> None:
    op.drop_column("notice_score", "sllm_confidence")
    op.drop_column("notice", "sllm_topic_checked_at")
