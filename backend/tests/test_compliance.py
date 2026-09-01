"""advisory INBOX #6(2026-09-01) 완료조건: robots.txt가 조용히 바뀌어도 사람이 알아채도록 —
분기별 재확인 도구가 해시 변경을 감지하면 소스를 자동 비활성화하고 audit_log에 남긴다."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from unittest import mock

from sqlalchemy import delete, insert, select

from app.collector.compliance import check_source
from app.db import engine
from app.models import audit_log, source

SOURCE_NAME = "IRIS 접수예정"


def _iris_source_id() -> int:
    with engine.connect() as conn:
        row = conn.execute(select(source.c.id).where(source.c.name == SOURCE_NAME)).first()
    assert row, "U2 시드가 먼저 실행돼 있어야 함"
    return row[0]


def _mock_robots(body: bytes):
    response = mock.Mock()
    response.content = body
    return mock.Mock(return_value=response)


def test_check_source_records_hash_and_verified_at_on_first_check(monkeypatch):
    source_id = _iris_source_id()
    monkeypatch.setattr("app.collector.compliance.url_guard.fetch", _mock_robots(b"User-agent: *\nAllow: /"))

    with engine.begin() as conn:
        conn.execute(source.update().where(source.c.id == source_id).values(robots_hash=None, active=True))
        result = check_source(conn, source_id)
        row = conn.execute(select(source.c.robots_hash, source.c.legal_verified_at, source.c.active).where(source.c.id == source_id)).one()

    assert result["fetch_ok"] is True
    assert result["changed"] is False  # 이전 해시가 없었으니 "변경"으로 볼 수 없음(비교 대상 없음)
    assert row.robots_hash is not None
    assert row.legal_verified_at is not None
    assert row.active is True


def test_check_source_deactivates_and_logs_on_robots_change(monkeypatch):
    source_id = _iris_source_id()
    old_hash = "0" * 64  # 실제와 다른 임의 해시 — 다음 확인에서 반드시 "변경"으로 잡히게

    with engine.begin() as conn:
        conn.execute(source.update().where(source.c.id == source_id).values(robots_hash=old_hash, active=True))

    monkeypatch.setattr("app.collector.compliance.url_guard.fetch", _mock_robots(b"User-agent: *\nDisallow: /"))

    try:
        with engine.begin() as conn:
            result = check_source(conn, source_id)
            row = conn.execute(select(source.c.robots_hash, source.c.active).where(source.c.id == source_id)).one()
            alert = conn.execute(
                select(audit_log.c.action)
                .where(audit_log.c.target_type == "source", audit_log.c.target_id == str(source_id), audit_log.c.action == "source.compliance_alert")
                .order_by(audit_log.c.id.desc())
            ).first()

        assert result["changed"] is True
        assert row.active is False
        assert row.robots_hash != old_hash
        assert alert is not None
    finally:
        with engine.begin() as conn:
            conn.execute(delete(audit_log).where(audit_log.c.target_type == "source", audit_log.c.target_id == str(source_id)))
            conn.execute(source.update().where(source.c.id == source_id).values(active=True, robots_hash=None))


def test_check_source_marks_fetch_failure_without_deactivating(monkeypatch):
    source_id = _iris_source_id()
    monkeypatch.setattr(
        "app.collector.compliance.url_guard.fetch", mock.Mock(side_effect=RuntimeError("타임아웃"))
    )

    with engine.begin() as conn:
        conn.execute(source.update().where(source.c.id == source_id).values(active=True))
        result = check_source(conn, source_id)
        row = conn.execute(select(source.c.active).where(source.c.id == source_id)).one()

    assert result["fetch_ok"] is False
    assert result["changed"] is False
    assert row.active is True  # 확인 실패는 "변경 감지"가 아니라서 비활성화하지 않음
