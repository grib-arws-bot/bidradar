"""app/cli.py의 collect() 서비스키 정규화 검증 — 2026-09-10 prod 최초 배포 시 실제 발생한
"SERVICE_KEY_IS_NOT_REGISTERED_ERROR" 재현. data.go.kr 마이페이지가 주는 "Encoding" 형태
(%2B·%3D 등)를 그대로 붙여넣으면 url_guard.fetch()가 다시 인코딩해 이중 인코딩되던 문제 —
collect()가 저장 전에 항상 unquote()해서 "Decoding" 형태로 통일하는지 확인한다."""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from sqlalchemy import delete, insert, select

from app.cli import collect
from app.db import engine
from app.models import source, source_credential


def _make_temp_source_with_credential(conn) -> int:
    source_id = conn.execute(
        insert(source)
        .values(
            name="_테스트_CLI_서비스키", org_name="테스트기관", channel_name="테스트기관",
            base_url="https://apis.data.go.kr/test/cli", stage="입찰공고",
            adapter_type="openapi", frequency_minutes=1440, is_system=False, skip_l1=True, active=True,
            legal_tier="A", auto_extract=False, auto_analyze=False,
        )
        .returning(source.c.id)
    ).scalar_one()
    conn.execute(insert(source_credential).values(source_id=source_id, kind="service_key", value=""))
    return source_id


def test_collect_decodes_percent_encoded_service_key_before_storing():
    with engine.begin() as conn:
        source_id = _make_temp_source_with_credential(conn)

    try:
        # 실제 발생 사례와 동일한 형태 — %2B(=+), %3D%3D(==)가 섞인 "Encoding" 키.
        encoded_key = "abcXYZ123%2Bdef%3D%3D"
        with mock.patch("app.collector.runner.run_source_and_process_pending") as mock_run:
            mock_run.return_value = {"fetched": 0, "inserted": 0, "skipped": 0, "scored": 0, "out_of_window": 0, "already_closed": 0, "dedup_notices_updated": 0, "dedup_groups_with_duplicates": 0, "extraction_candidates": 0, "auto_extracted": 0, "analyze_candidates": 0, "auto_analyzed": 0}
            collect(source_id, encoded_key, False, None)

        with engine.connect() as conn:
            stored = conn.execute(
                select(source_credential.c.value).where(
                    source_credential.c.source_id == source_id, source_credential.c.kind == "service_key"
                )
            ).scalar_one()
        assert stored == "abcXYZ123+def=="
    finally:
        with engine.begin() as conn:
            conn.execute(delete(source_credential).where(source_credential.c.source_id == source_id))
            conn.execute(delete(source).where(source.c.id == source_id))


def test_collect_leaves_already_decoded_service_key_unchanged():
    with engine.begin() as conn:
        source_id = _make_temp_source_with_credential(conn)

    try:
        decoded_key = "abcXYZ123+def=="
        with mock.patch("app.collector.runner.run_source_and_process_pending") as mock_run:
            mock_run.return_value = {"fetched": 0, "inserted": 0, "skipped": 0, "scored": 0, "out_of_window": 0, "already_closed": 0, "dedup_notices_updated": 0, "dedup_groups_with_duplicates": 0, "extraction_candidates": 0, "auto_extracted": 0, "analyze_candidates": 0, "auto_analyzed": 0}
            collect(source_id, decoded_key, False, None)

        with engine.connect() as conn:
            stored = conn.execute(
                select(source_credential.c.value).where(
                    source_credential.c.source_id == source_id, source_credential.c.kind == "service_key"
                )
            ).scalar_one()
        assert stored == decoded_key
    finally:
        with engine.begin() as conn:
            conn.execute(delete(source_credential).where(source_credential.c.source_id == source_id))
            conn.execute(delete(source).where(source.c.id == source_id))
