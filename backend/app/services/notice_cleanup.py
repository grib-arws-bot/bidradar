"""공고 보존 정책(2026-09-04 사용자 결정) — 마감일이 지난 공고는 BidRadar 취지("이미 늦기
전에 본다")상 더 이상 참여 판단에 쓸모가 없다. 마감 후 DEFAULT_RETENTION_DAYS가 지나면
삭제한다. close_dt가 없는 공고(마감일 자체가 없는 소스, INBOX #1)는 "마감됐다"고 판단할
근거가 없어 대상에서 제외한다.

analysis·award는 notice.id에 ON DELETE CASCADE가 안 걸려 있어(analysis는 url/upload 입력도
받아 notice_id가 nullable, award는 애초에 설정 안 됨) 먼저 명시적으로 지운다 — 나머지
(notice_score·requirement·classification_correction)는 스키마상 CASCADE라 notice 삭제 시
자동으로 같이 지워진다.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Connection

from app.models import analysis, award, notice

DEFAULT_RETENTION_DAYS = 30


def delete_expired_notices(conn: Connection, retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
    """close_dt가 retention_days일 이전에 이미 지난 공고를 삭제하고 삭제 건수를 반환한다."""
    expired_ids = [
        row.id
        for row in conn.execute(
            select(notice.c.id).where(
                notice.c.close_dt.isnot(None),
                notice.c.close_dt < func.now() - timedelta(days=retention_days),
            )
        )
    ]
    if not expired_ids:
        return 0
    conn.execute(delete(analysis).where(analysis.c.notice_id.in_(expired_ids)))
    conn.execute(delete(award).where(award.c.notice_id.in_(expired_ids)))
    conn.execute(delete(notice).where(notice.c.id.in_(expired_ids)))
    return len(expired_ids)
