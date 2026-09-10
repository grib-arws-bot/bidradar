"""공고 상세페이지의 관심주제 직접 수정(2026-09-05, 사용자 지시) — 기존 S1 분류검수
(app/services/classification.py, classification_correction 감사로그)와는 다른 목적이다.
분류검수는 "나중에 규칙을 고칠 근거를 남기는 감사로그"이고, 이건 notice_score를 그 자리에서
바로 add/remove하는 실제 편집이다(카드의 4개 아이콘 액션을 없애면서 대체로 도입)."""

from __future__ import annotations

from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Connection

from app.models import notice_score

# rule_ver=0은 "사람이 수동으로 추가함"을 나타낸다 — score_l2의 규칙판(rule_ver=1)과 구분해서
# 나중에 "왜 이 주제가 붙었는지" 추적할 수 있게 한다.
MANUAL_RULE_VER = 0
MANUAL_REASON = "관리자 수동 추가"


def add_topic(conn: Connection, notice_id: int, topic_id: int) -> bool:
    """이미 붙어 있으면 아무것도 안 하고 False. 새로 추가했으면 True."""
    existing = conn.execute(
        select(notice_score.c.id).where(
            notice_score.c.notice_id == notice_id, notice_score.c.interest_topic_id == topic_id
        )
    ).first()
    if existing:
        return False
    conn.execute(
        insert(notice_score).values(
            notice_id=notice_id,
            interest_topic_id=topic_id,
            l2_score=99,  # 사람이 직접 붙인 것이라 규칙 점수 범위보다 확실히 높은 값으로 구분
            reason=MANUAL_REASON,
            rule_ver=MANUAL_RULE_VER,
        )
    )
    return True


def remove_topic(conn: Connection, notice_id: int, topic_id: int) -> bool:
    """제거했으면 True, 원래 없었으면 False."""
    result = conn.execute(
        delete(notice_score).where(
            notice_score.c.notice_id == notice_id, notice_score.c.interest_topic_id == topic_id
        )
    )
    return result.rowcount > 0
