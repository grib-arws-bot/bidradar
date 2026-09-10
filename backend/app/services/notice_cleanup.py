"""공고 보존 정책(2026-09-04 사용자 결정, 2026-09-10 기준 변경) — 마감일이 지난 공고는
BidRadar 취지("이미 늦기 전에 본다")상 더 이상 참여 판단에 쓸모가 없다.

- close_dt가 있는 공고: 마감 후 CLOSE_RETENTION_DAYS(기본 3일)가 지나면 삭제.
- close_dt가 없는 공고(마감일 자체가 없는 소스 — 발주계획·사전규격·IRIS 등, INBOX #1): "마감됐다"고
  판단할 근거가 없으므로 대신 "공고일" 기준으로 NO_CLOSE_RETENTION_DAYS(기본 60일=2개월)가 지나면
  삭제한다. "공고일"은 notice_query.py의 기본 정렬(notice_date_desc)과 같은 값 —
  extra.ancmDe(IRIS) 또는 extra.nticeDt(발주계획)이며, 이 값도 없는 소스(사전규격 등)는
  open_dt(게시일)로 대신한다 — 셋 다 없는 경우는 판단 근거가 없어 삭제 대상에서 제외한다.

2026-09-10부터 이 두 정책은 `app.collector.runner.run_source()`가 매 수집 직후 자동으로
실행한다(사용자 지시 — "오래된 데이터는 자동으로 삭제되어야 해") — 별도 스케줄러 인프라가
아직 없어(구현스펙 참고) 아직은 "수집이 실행될 때마다" 같이 도는 방식으로 자동화한다. CLI
`cleanup-closed`는 수동으로 즉시 돌리고 싶을 때·수집 자체가 오래 안 도는 소스를 정리할 때 쓴다.

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

CLOSE_RETENTION_DAYS = 3
NO_CLOSE_RETENTION_DAYS = 60

# 하위 호환(기존 CLI 인자 기본값 등에서 참조) — CLOSE_RETENTION_DAYS의 별칭.
DEFAULT_RETENTION_DAYS = CLOSE_RETENTION_DAYS

_NOTICE_DATE = func.coalesce(notice.c.extra["ancmDe"].astext, notice.c.extra["nticeDt"].astext, func.to_char(notice.c.open_dt, "YYYY-MM-DD"))


def _delete_notice_ids(conn: Connection, ids: list[int]) -> int:
    if not ids:
        return 0
    conn.execute(delete(analysis).where(analysis.c.notice_id.in_(ids)))
    conn.execute(delete(award).where(award.c.notice_id.in_(ids)))
    conn.execute(delete(notice).where(notice.c.id.in_(ids)))
    return len(ids)


def delete_expired_notices(
    conn: Connection,
    retention_days: int = CLOSE_RETENTION_DAYS,
    *,
    no_close_retention_days: int = NO_CLOSE_RETENTION_DAYS,
) -> int:
    """마감(close_dt) 후 retention_days일이 지난 공고와, 마감일이 없어 대신 공고일 기준
    no_close_retention_days일이 지난 공고를 함께 삭제하고 총 삭제 건수를 반환한다."""
    closed_expired_ids = [
        row.id
        for row in conn.execute(
            select(notice.c.id).where(
                notice.c.close_dt.isnot(None),
                notice.c.close_dt < func.now() - timedelta(days=retention_days),
            )
        )
    ]
    no_close_expired_ids = [
        row.id
        for row in conn.execute(
            select(notice.c.id).where(
                notice.c.close_dt.is_(None),
                _NOTICE_DATE.isnot(None),
                _NOTICE_DATE < func.to_char(func.now() - timedelta(days=no_close_retention_days), "YYYY-MM-DD"),
            )
        )
    ]
    return _delete_notice_ids(conn, closed_expired_ids) + _delete_notice_ids(conn, no_close_expired_ids)
