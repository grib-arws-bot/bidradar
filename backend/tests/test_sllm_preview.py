"""사내 sLLM(A, extract-requirements) 요구사항 추출 미리보기 — app/services/analysis/sllm_preview.py
검증. 실제 sLLM 서버에 나가지 않는다 — sllm_client 함수를 모킹해서 job 시작/폴링·근거
검증(sanitize_sllm_requirements는 실제 로직 그대로 사용)·중복 실행 거부만 확인한다.
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")
os.environ.setdefault("ADMIN_EMAIL", "report@grib.co.kr")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$argon2id$v=19$m=65536,t=3,p=4$9/7/Wg+VSkOsVCeiQiCz7w$bdDzJi9bKuERjBb6NHN0Ztk+X6uwxugL7kViHVRiqnY",
)

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, select

from app.db import engine
from app.main import app
from app.models import analysis, analysis_doc, analysis_sllm_preview, notice, source
from app.services.analysis.sllm_preview import (
    SllmPreviewInProgressError,
    get_sllm_preview_for_notice,
    start_sllm_preview_for_notice,
)
from app.services.sllm_client import SllmError, SllmNotConfiguredError

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"

_SOURCE_TEXT = "제3장 기술 규격\n(1) 처리 용량은 초당 30프레임 이상이어야 한다."


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    return c


def _any_source_id(conn) -> int:
    return conn.execute(select(source.c.id).limit(1)).scalar_one()


@pytest.fixture
def done_analysis():
    """A1이 이미 성공적으로 끝난 상태(analysis_doc에 텍스트가 있음)를 흉내 낸다."""
    with engine.begin() as conn:
        notice_id = conn.execute(
            insert(notice).values(
                source_id=_any_source_id(conn), source_ver=1, stage="입찰공고", title="[테스트] sLLM 미리보기 검증용 임시 공고",
                url="https://example.grib-test.kr/notice/sllm-preview-test",
            ).returning(notice.c.id)
        ).scalar_one()
        analysis_id = conn.execute(
            insert(analysis).values(
                notice_id=notice_id, source_kind="notice", input_ref="x", status="done", step="A1_extract", ver=1,
            ).returning(analysis.c.id)
        ).scalar_one()
        conn.execute(
            insert(analysis_doc).values(
                analysis_id=analysis_id, name="규격서.hwpx", kind="hwpx", bytes=100, sha256="x" * 64,
                extract_method="hwpx_xml", extract_ok=True, text=_SOURCE_TEXT,
            )
        )
    yield notice_id, analysis_id
    with engine.begin() as conn:
        conn.execute(delete(analysis).where(analysis.c.id == analysis_id))  # cascade로 doc·preview도 지움
        conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_start_requires_prior_extraction():
    with engine.begin() as conn:
        with pytest.raises(ValueError, match="첨부문서 추출"):
            start_sllm_preview_for_notice(conn, notice_id=999999999)


def test_start_creates_running_preview_and_records_job_id(done_analysis):
    notice_id, analysis_id = done_analysis
    with mock.patch(
        "app.services.analysis.sllm_preview.start_extract_requirements",
        return_value={"job_id": "job-abc", "status": "queued", "trace_id": f"a_preview_{analysis_id}"},
    ) as mock_start:
        with engine.begin() as conn:
            result = start_sllm_preview_for_notice(conn, notice_id)

    assert result["status"] == "queued"
    mock_start.assert_called_once()
    assert _SOURCE_TEXT in mock_start.call_args.args[0]  # _collect_source_text가 "=== 파일명 ===" 헤더를 덧붙임
    with engine.connect() as conn:
        row = conn.execute(
            select(analysis_sllm_preview.c.status, analysis_sllm_preview.c.sllm_job_id)
            .where(analysis_sllm_preview.c.analysis_id == analysis_id)
        ).mappings().one()
    assert row["status"] == "queued"
    assert row["sllm_job_id"] == "job-abc"


def test_start_rejects_duplicate_while_running(done_analysis):
    notice_id, analysis_id = done_analysis
    with mock.patch(
        "app.services.analysis.sllm_preview.start_extract_requirements",
        return_value={"job_id": "job-abc", "status": "running"},
    ):
        with engine.begin() as conn:
            start_sllm_preview_for_notice(conn, notice_id)

        with pytest.raises(SllmPreviewInProgressError):
            with engine.begin() as conn:
                start_sllm_preview_for_notice(conn, notice_id)


def test_get_returns_none_without_preview(done_analysis):
    notice_id, _analysis_id = done_analysis
    with engine.begin() as conn:
        assert get_sllm_preview_for_notice(conn, notice_id) is None


def test_get_polls_and_sanitizes_on_done(done_analysis):
    notice_id, analysis_id = done_analysis
    with mock.patch(
        "app.services.analysis.sllm_preview.start_extract_requirements",
        return_value={"job_id": "job-abc", "status": "running"},
    ):
        with engine.begin() as conn:
            start_sllm_preview_for_notice(conn, notice_id)

    raw_requirements = [
        {"category": "성능", "req_text": "초당 30프레임 이상", "op": "gte", "cite": "(1) 처리 용량은 초당 30프레임 이상이어야 한다."},  # 원문에 실제로 있음 — 통과
        {"category": "성능", "req_text": "환각 요구사항", "op": "manual", "cite": "존재하지 않는 조문"},  # 원문에 없음 — 탈락
    ]
    with mock.patch(
        "app.services.analysis.sllm_preview.get_extract_requirements_status",
        return_value={"status": "done", "chunks_processed": 1, "chunks_total": 1, "output": {"requirements": raw_requirements}},
    ):
        with engine.begin() as conn:
            result = get_sllm_preview_for_notice(conn, notice_id)

    assert result["status"] == "done"
    assert len(result["requirements"]) == 1
    assert result["requirements"][0]["req_text"] == "초당 30프레임 이상"
    assert result["rejected_ungrounded_count"] == 1
    assert result["duplicate_count"] == 0


def test_get_keeps_running_state_when_poll_fails_transiently(done_analysis):
    notice_id, analysis_id = done_analysis
    with mock.patch(
        "app.services.analysis.sllm_preview.start_extract_requirements",
        return_value={"job_id": "job-abc", "status": "running"},
    ):
        with engine.begin() as conn:
            start_sllm_preview_for_notice(conn, notice_id)

    with mock.patch(
        "app.services.analysis.sllm_preview.get_extract_requirements_status",
        side_effect=SllmNotConfiguredError("설정 안 됨"),
    ):
        with engine.begin() as conn:
            result = get_sllm_preview_for_notice(conn, notice_id)

    assert result["status"] == "running"  # 실패로 단정하지 않고 그대로 유지


def test_get_marks_failed_when_job_not_found(done_analysis):
    """2026-09-20 실측 발견 — sLLM 서버가 재시작되며(GPU 전환) 진행 중이던 job의 상태가
    사라져 job_not_found가 나는 사례가 실제로 있었다. 이건 일시적 오류와 달리 그 job이
    다시는 안 돌아오므로, "진행 중" 상태를 그대로 두면(기존 버그) 화면이 영원히 "처리
    중..."에 멈춘다 — 즉시 실패로 확정해야 한다."""
    notice_id, analysis_id = done_analysis
    with mock.patch(
        "app.services.analysis.sllm_preview.start_extract_requirements",
        return_value={"job_id": "job-abc", "status": "running"},
    ):
        with engine.begin() as conn:
            start_sllm_preview_for_notice(conn, notice_id)

    with mock.patch(
        "app.services.analysis.sllm_preview.get_extract_requirements_status",
        side_effect=SllmError("job_not_found", "존재하지 않거나 만료된 job_id입니다"),
    ):
        with engine.begin() as conn:
            result = get_sllm_preview_for_notice(conn, notice_id)

    assert result["status"] == "failed"
    assert "다시 시도" in result["error"]


def test_get_marks_failed_when_job_interrupted(done_analysis):
    """2026-09-20 sLLM팀 후속 조치 — job 상태를 파일로 영속화하고, 서버 재시작으로 중단된
    job은 job_not_found 대신 error.code="interrupted"로 명확히 응답하도록 개선됨. 이것도
    job_not_found와 동일하게(다시 안 돌아오는 job) 즉시 실패로 확정해야 한다."""
    notice_id, analysis_id = done_analysis
    with mock.patch(
        "app.services.analysis.sllm_preview.start_extract_requirements",
        return_value={"job_id": "job-abc", "status": "running"},
    ):
        with engine.begin() as conn:
            start_sllm_preview_for_notice(conn, notice_id)

    with mock.patch(
        "app.services.analysis.sllm_preview.get_extract_requirements_status",
        side_effect=SllmError("interrupted", "서버 재시작으로 처리가 중단됐습니다 — 다시 요청해주세요"),
    ):
        with engine.begin() as conn:
            result = get_sllm_preview_for_notice(conn, notice_id)

    assert result["status"] == "failed"
    assert "다시 시도" in result["error"]


def test_get_keeps_running_state_when_connection_fails_transiently(done_analysis):
    """2026-09-21 실측 발견(공고 1699) — sLLM 서버 연결 실패 시 url_guard.fetch()가 raw
    requests.exceptions.ConnectionError를 그대로 올리는데, 기존 코드는 이걸 못 잡아서
    API가 500으로 터졌다. job_not_found와 달리 일시적 문제이므로 진행 중 상태를 유지해야
    한다."""
    notice_id, analysis_id = done_analysis
    with mock.patch(
        "app.services.analysis.sllm_preview.start_extract_requirements",
        return_value={"job_id": "job-abc", "status": "running"},
    ):
        with engine.begin() as conn:
            start_sllm_preview_for_notice(conn, notice_id)

    with mock.patch(
        "app.services.analysis.sllm_preview.get_extract_requirements_status",
        side_effect=requests.exceptions.ConnectionError("Connection refused"),
    ):
        with engine.begin() as conn:
            result = get_sllm_preview_for_notice(conn, notice_id)

    assert result["status"] == "running"


def test_sllm_requirements_route_requires_prior_extraction(client: TestClient):
    with engine.begin() as conn:
        notice_id = conn.execute(
            insert(notice).values(
                source_id=_any_source_id(conn), source_ver=1, stage="입찰공고", title="[테스트] A1 미실행 공고",
                url="https://example.grib-test.kr/notice/sllm-preview-404",
            ).returning(notice.c.id)
        ).scalar_one()
    try:
        resp = client.post(f"/api/notices/{notice_id}/sllm-requirements")
        assert resp.status_code == 404
    finally:
        with engine.begin() as conn:
            conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_sllm_requirements_route_happy_path(done_analysis, client: TestClient):
    notice_id, _analysis_id = done_analysis
    with mock.patch(
        "app.services.analysis.sllm_preview.start_extract_requirements",
        return_value={"job_id": "job-abc", "status": "queued"},
    ):
        start_resp = client.post(f"/api/notices/{notice_id}/sllm-requirements")
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "queued"

    with mock.patch(
        "app.services.analysis.sllm_preview.get_extract_requirements_status",
        return_value={"status": "done", "chunks_processed": 1, "chunks_total": 1, "output": {"requirements": []}},
    ):
        get_resp = client.get(f"/api/notices/{notice_id}/sllm-requirements")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "done"
