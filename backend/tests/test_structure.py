"""S8 A2(요구사양 구조화, LLM) — app/services/analysis/structure.py 검증.

실제 api.anthropic.com에 나가지 않는다 — url_guard.fetch를 모킹해서 유효성 검증(cite 없는
항목 제외)·판정 필드 미기록(원칙 1)·토큰/비용 기록·중복 실행 거부만 확인한다.
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
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, select

from app.config import settings
from app.db import engine
from app.main import app
from app.models import analysis, analysis_doc, analysis_requirement, notice, source
from app.services.analysis.structure import (
    LLMNotConfiguredError,
    StructuringInProgressError,
    run_structuring,
)

EMAIL = "report@grib.co.kr"
PASSWORD = "dev-local-test-pw-123"


@pytest.fixture
def client() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    return c


def _any_source_id(conn) -> int:
    return conn.execute(select(source.c.id).limit(1)).scalar_one()


def _mock_anthropic_response(requirements: list[dict], input_tokens: int = 1000, output_tokens: int = 200) -> mock.Mock:
    resp = mock.Mock()
    resp.json.return_value = {
        "content": [{"type": "tool_use", "name": "extract_requirements", "input": {"requirements": requirements}}],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }
    return resp


@pytest.fixture
def done_analysis():
    """A1이 이미 성공적으로 끝난 상태(analysis_doc에 텍스트가 있음)를 흉내 낸다."""
    with engine.begin() as conn:
        notice_id = conn.execute(
            insert(notice).values(
                source_id=_any_source_id(conn), source_ver=1, stage="입찰공고", title="[테스트] A2 구조화 검증용 임시 공고",
                url="https://example.grib-test.kr/notice/structure-test",
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
                extract_method="hwpx_xml", extract_ok=True, text="제3장 기술 규격\n(1) 처리 용량은 초당 30프레임 이상이어야 한다.",
            )
        )
    yield analysis_id
    with engine.begin() as conn:
        conn.execute(delete(analysis).where(analysis.c.id == analysis_id))  # cascade로 doc·requirement도 지움
        conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_run_structuring_requires_api_key(done_analysis, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with engine.begin() as conn:
        with pytest.raises(LLMNotConfiguredError):
            run_structuring(conn, done_analysis)


def test_run_structuring_rejects_unknown_model(done_analysis, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.begin() as conn:
        with pytest.raises(ValueError, match="허용되지 않은 모델"):
            run_structuring(conn, done_analysis, model="gpt-4")


def test_run_structuring_saves_valid_items_and_skips_missing_cite(done_analysis, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    raw_items = [
        {
            "category": "성능", "req_text": "처리 용량 초당 30프레임 이상", "req_value": "30", "req_unit": "fps",
            "op": "gte", "cite": "제3장 (1)",
            "judgement": "ok",  # LLM이 실수로 판정을 끼워 넣어도 무시해야 함(원칙 1)
        },
        {"category": "기타", "req_text": "근거 위치를 특정 못 한 항목", "op": "manual", "cite": ""},  # cite 없음 → 제외
    ]
    with mock.patch(
        "app.services.analysis.structure.fetch", return_value=_mock_anthropic_response(raw_items)
    ) as mock_fetch:
        with engine.begin() as conn:
            result = run_structuring(conn, done_analysis)

    assert mock_fetch.call_args.kwargs["headers"]["x-api-key"] == "sk-ant-test"
    assert result == {
        "analysis_id": done_analysis, "extracted": 2, "saved": 1, "skipped_no_cite": 1,
        "input_tokens": 1000, "output_tokens": 200, "cost_usd": round(1000 / 1e6 * 1.00 + 200 / 1e6 * 5.00, 4),
    }

    with engine.connect() as conn:
        saved = conn.execute(
            select(analysis_requirement).where(analysis_requirement.c.analysis_id == done_analysis)
        ).mappings().all()
        updated = conn.execute(select(analysis.c.status, analysis.c.step, analysis.c.llm_tokens, analysis.c.llm_cost).where(analysis.c.id == done_analysis)).first()

    assert len(saved) == 1
    assert saved[0]["req_text"] == "처리 용량 초당 30프레임 이상"
    # 원칙 1 — LLM이 뭐라 보내든 judgement/matched_product_id는 항상 테이블 기본값이어야 한다.
    assert saved[0]["judgement"] == "unknown"
    assert saved[0]["matched_product_id"] is None
    assert updated.status == "done"
    assert updated.step == "A2_structure"
    assert updated.llm_tokens == 1200


def test_run_structuring_rejects_duplicate_run(done_analysis, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    raw_items = [{"category": "성능", "req_text": "t", "op": "manual", "cite": "1"}]
    with mock.patch("app.services.analysis.structure.fetch", return_value=_mock_anthropic_response(raw_items)):
        with engine.begin() as conn:
            run_structuring(conn, done_analysis)

    with engine.begin() as conn:
        with pytest.raises(StructuringInProgressError):
            run_structuring(conn, done_analysis)


def test_run_structuring_fails_cleanly_without_extracted_text(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.begin() as conn:
        notice_id = conn.execute(
            insert(notice).values(
                source_id=_any_source_id(conn), source_ver=1, stage="입찰공고", title="[테스트] A2 텍스트 없음 검증용",
                url="https://example.grib-test.kr/notice/structure-empty",
            ).returning(notice.c.id)
        ).scalar_one()
        analysis_id = conn.execute(
            insert(analysis).values(notice_id=notice_id, source_kind="notice", input_ref="x", status="done", ver=1)
            .returning(analysis.c.id)
        ).scalar_one()
    try:
        with engine.begin() as conn:
            with pytest.raises(ValueError, match="추출된 문서 텍스트가 없어"):
                run_structuring(conn, analysis_id)
    finally:
        with engine.begin() as conn:
            conn.execute(delete(analysis).where(analysis.c.id == analysis_id))
            conn.execute(delete(notice).where(notice.c.id == notice_id))


def test_run_structuring_records_failure_on_llm_error(done_analysis, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with mock.patch("app.services.analysis.structure.fetch", side_effect=RuntimeError("네트워크 실패")):
        with engine.begin() as conn:
            with pytest.raises(RuntimeError):
                run_structuring(conn, done_analysis)

    with engine.connect() as conn:
        row = conn.execute(select(analysis.c.status, analysis.c.step, analysis.c.verdict).where(analysis.c.id == done_analysis)).first()
    assert row.status == "failed"
    assert row.step == "A2_structure"
    assert "네트워크 실패" in row.verdict


# ---- API 라우트(POST /structure, GET /requirements) -------------------------------


def _notice_id_of(analysis_id: int) -> int:
    with engine.connect() as conn:
        return conn.execute(select(analysis.c.notice_id).where(analysis.c.id == analysis_id)).scalar_one()


def test_structure_route_requires_auth():
    response = TestClient(app).post("/api/notices/1/structure", json={"model": "haiku"})
    assert response.status_code == 401


def test_requirements_route_requires_auth():
    response = TestClient(app).get("/api/notices/1/requirements")
    assert response.status_code == 401


def test_requirements_route_returns_none_without_analysis(client: TestClient):
    assert client.get("/api/notices/999999999/requirements").json() is None


def test_structure_route_404_without_prior_extraction(client: TestClient):
    response = client.post("/api/notices/999999999/structure", json={"model": "haiku"})
    assert response.status_code == 404


def test_structure_route_happy_path_then_requirements_visible(done_analysis, monkeypatch, client: TestClient):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    notice_id = _notice_id_of(done_analysis)
    raw_items = [{"category": "성능", "req_text": "초당 30프레임 이상", "req_value": "30", "req_unit": "fps", "op": "gte", "cite": "제3장 (1)"}]

    with mock.patch("app.services.analysis.structure.fetch", return_value=_mock_anthropic_response(raw_items)):
        response = client.post(f"/api/notices/{notice_id}/structure", json={"model": "haiku"})
    assert response.status_code == 200
    assert response.json()["saved"] == 1

    got = client.get(f"/api/notices/{notice_id}/requirements").json()
    assert got["analysis_id"] == done_analysis
    assert len(got["requirements"]) == 1
    assert got["requirements"][0]["req_text"] == "초당 30프레임 이상"
    # A2 단계는 판정을 안 하므로 judgement/matched_product_id는 응답에 아예 없어야 한다 —
    # "unknown"이라도 화면에 보이면 마치 판정된 것처럼 오해를 줄 수 있음.
    assert "judgement" not in got["requirements"][0]
    assert "matched_product_id" not in got["requirements"][0]

    # 같은 분석에 재실행하면 409(중복 실행 거부, 비용 재발생 방지)
    conflict = client.post(f"/api/notices/{notice_id}/structure", json={"model": "haiku"})
    assert conflict.status_code == 409


def test_structure_route_501_without_api_key(done_analysis, monkeypatch, client: TestClient):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    notice_id = _notice_id_of(done_analysis)
    response = client.post(f"/api/notices/{notice_id}/structure", json={"model": "haiku"})
    assert response.status_code == 501
