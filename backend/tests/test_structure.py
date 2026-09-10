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
from app.models import analysis, analysis_doc, analysis_requirement, interest_topic, notice, notice_score, source
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


_SAMPLE_SUMMARY = {
    "project_period": "5년 이내(당해 9개월 이내)",
    "project_budget": "150억원 이내(당해 19억원)",
    "purpose": "연안하구 시스템 변화 프로세스 규명",
    "sub_business": "연안하구 관리기술 개발",
    "task_type": {"execution_system": "일반형", "development_form": "원천기술형", "call_type": "지정공모형"},
    "contact": {"department": "생명환경팀", "role": "담당자", "phone": "02-3460-0312", "email": "sm7289@kimst.re.kr"},
    "content_items": [
        {
            "title": "연안하구 관리기술 개발", "summary": "관측·분석기술 개발을 목표로 한다.", "period": "5년 이내", "budget": "150억원 이내",
            "task_type": {"execution_system": "일반형", "development_form": "원천기술형", "call_type": "지정공모형"},
            "lead_org": "제한없음",
        },
    ],
    "evaluation": [{"item": "연구개발", "weight": "40%", "note": "계획 구체성 등"}],
    "budget_conditions": {
        "government_support_ratio": "국제공동연구개발비 제외 연구개발비의 75% 이하",
        "institution_cash_burden_ratio": "기관부담연구개발비의 10% 이상",
        "tech_fee_collection": "징수함",
        "youth_hiring_requirement": "정부지원연구개발비 5억원당 1명, 만 18~34세, 1년 이상 고용",
        "labor_cost_basis": "신규채용 참여연구자 등 예외 조건에서만 현금 계상 가능, 계상률 총합 100% 이내",
    },
    "eligibility": {
        "consortium": "산학연 컨소시엄 필수", "lead_org": "제한 없음", "participant_org": "산학연",
        "demand_org": "해당 없음", "company_size": "중소·중견기업", "special_notes": "",
    },
    "submission": {"deadline": "2026.9.9 16:00", "method": "IRIS 온라인 접수", "documents": ["연구개발계획서", "참여의사 확인서"]},
    "other_notes": "",
}


def _mock_anthropic_response(
    requirements: list[dict], summary: dict | None = None, input_tokens: int = 1000, output_tokens: int = 200
) -> mock.Mock:
    resp = mock.Mock()
    resp.json.return_value = {
        "content": [
            {
                "type": "tool_use",
                "name": "extract_requirements",
                "input": {"requirements": requirements, "summary": summary if summary is not None else _SAMPLE_SUMMARY},
            }
        ],
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
            "op": "gte", "cite": "제3장 (1)", "task_ref": "연안하구 관리기술 개발",
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
    # topics_added는 공유 개발 DB의 실제 keyword_rule 내용에 따라 달라질 수 있어 정확한 값 대신
    # 타입만 확인한다(2026-09-05, AI분석 후 내용 기반 관심주제 재매칭 도입 — test_structure_records_new_interest_topic_from_content 참고).
    topics_added = result.pop("topics_added")
    assert isinstance(topics_added, int) and topics_added >= 0
    assert result == {
        "analysis_id": done_analysis, "extracted": 2, "saved": 1, "skipped_no_cite": 1,
        "input_tokens": 1000, "output_tokens": 200, "cost_usd": round(1000 / 1e6 * 1.00 + 200 / 1e6 * 5.00, 4),
    }

    with engine.connect() as conn:
        saved = conn.execute(
            select(analysis_requirement).where(analysis_requirement.c.analysis_id == done_analysis)
        ).mappings().all()
        updated = conn.execute(
            select(analysis.c.status, analysis.c.step, analysis.c.llm_tokens, analysis.c.llm_cost, analysis.c.summary)
            .where(analysis.c.id == done_analysis)
        ).first()

    assert len(saved) == 1
    assert saved[0]["req_text"] == "처리 용량 초당 30프레임 이상"
    assert saved[0]["task_ref"] == "연안하구 관리기술 개발"
    # 원칙 1 — LLM이 뭐라 보내든 judgement/matched_product_id는 항상 테이블 기본값이어야 한다.
    assert saved[0]["judgement"] == "unknown"
    assert saved[0]["matched_product_id"] is None
    assert updated.status == "done"
    assert updated.step == "A2_structure"
    assert updated.llm_tokens == 1200
    assert updated.summary == _SAMPLE_SUMMARY


def test_run_structuring_rescans_interest_topics_from_content_not_title(done_analysis, monkeypatch):
    """AI분석 후 내용 기반 관심주제 재매칭(2026-09-05, 사용자 지시) — 제목엔 "로봇"이 없지만
    A2가 뽑은 요약 내용에는 있으므로 새로 매칭돼야 한다."""
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.connect() as conn:
        notice_id, notice_title = conn.execute(
            select(analysis.c.notice_id, notice.c.title).join(notice, notice.c.id == analysis.c.notice_id).where(analysis.c.id == done_analysis)
        ).first()
    assert "로봇" not in notice_title  # 이 테스트의 전제 — 제목엔 없어야 "내용 기반"임이 증명됨

    summary = dict(_SAMPLE_SUMMARY, content_items=[
        {"title": "로봇 자동화 과제", "summary": "본 과제는 협동로봇 기반 자동화 기술을 개발한다.", "period": "1년", "budget": "10억원"},
    ])
    raw_items = [{"category": "성능", "req_text": "t", "op": "manual", "cite": "1"}]
    with mock.patch("app.services.analysis.structure.fetch", return_value=_mock_anthropic_response(raw_items, summary=summary)):
        with engine.begin() as conn:
            result = run_structuring(conn, done_analysis)

    assert result["topics_added"] >= 1
    with engine.connect() as conn:
        rows = conn.execute(
            select(interest_topic.c.name, notice_score.c.reason)
            .join(interest_topic, interest_topic.c.id == notice_score.c.interest_topic_id)
            .where(notice_score.c.notice_id == notice_id)
        ).all()
    names = [r.name for r in rows]
    assert "로봇/자동화" in names
    matched_row = next(r for r in rows if r.name == "로봇/자동화")
    assert "AI분석 내용 기반 매칭" in matched_row.reason


def test_run_structuring_does_not_duplicate_already_matched_topic(done_analysis, monkeypatch):
    """제목 기반 수집 시점 매칭이 이미 있는 주제는 내용 기반 재매칭에서 중복 추가하지 않는다."""
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with engine.connect() as conn:
        notice_id, topic_id = conn.execute(
            select(analysis.c.notice_id, interest_topic.c.id)
            .join(notice, notice.c.id == analysis.c.notice_id)
            .join(interest_topic, interest_topic.c.name == "로봇/자동화")
            .where(analysis.c.id == done_analysis)
        ).first()
    with engine.begin() as conn:
        conn.execute(
            insert(notice_score).values(
                notice_id=notice_id, interest_topic_id=topic_id, l2_score=4, reason="키워드 매칭: 로봇", rule_ver=1,
            )
        )

    summary = dict(_SAMPLE_SUMMARY, content_items=[
        {"title": "로봇 자동화 과제", "summary": "협동로봇 자동화 기술 개발", "period": "1년", "budget": "10억원"},
    ])
    raw_items = [{"category": "성능", "req_text": "t", "op": "manual", "cite": "1"}]
    with mock.patch("app.services.analysis.structure.fetch", return_value=_mock_anthropic_response(raw_items, summary=summary)):
        with engine.begin() as conn:
            run_structuring(conn, done_analysis)

    with engine.connect() as conn:
        count = conn.execute(
            select(notice_score.c.id).where(notice_score.c.notice_id == notice_id, notice_score.c.interest_topic_id == topic_id)
        ).all()
    assert len(count) == 1  # 중복 추가 안 됨


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
    # 호출부 계약: try/except는 반드시 with engine.begin() **안에**(같은 트랜잭션) 둬야 한다
    # (실제 호출부인 pending_analysis.py·notice_strategy.py가 이 형태를 따른다, 2026-09-08).
    # 밖에 두면 run_structuring이 다시 던진 예외가 이 with 블록을 통째로 롤백시켜, 방금 conn에
    # 기록한 "failed" 상태까지 같이 사라진다 — 아래 두 번째 테스트가 그 대조를 보여준다.
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


def test_run_structuring_failure_lost_if_caller_catches_outside_transaction(done_analysis, monkeypatch):
    """반례 — try/except를 with engine.begin() **밖에** 두면(잘못된 패턴) "failed" 기록이
    트랜잭션 롤백으로 사라져 "시도조차 안 한 것"과 구분 불가능해진다.

    2026-09-08 실측 — IRIS 접수예정 자동수집 중 공고 1건(id=39946)의 A2가 정확히 이 패턴
    때문에 흔적도 없이 조용히 스킵됐다(CLAUDE.md S8 "조용한 실패 금지" 위반). 원인이었던
    pending_analysis.py·notice_strategy.py 세 곳 모두 try/except를 with 블록 안으로
    옮겨 고쳤다 — 이 테스트는 "왜 밖에 두면 안 되는지"를 남겨두는 회귀 방지용 반례다."""
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    with mock.patch("app.services.analysis.structure.fetch", side_effect=RuntimeError("네트워크 실패")):
        try:
            with engine.begin() as conn:
                run_structuring(conn, done_analysis)
        except RuntimeError:
            pass

    with engine.connect() as conn:
        row = conn.execute(select(analysis.c.status, analysis.c.step).where(analysis.c.id == done_analysis)).first()
    # 롤백돼 done_analysis 픽스처가 만든 원래 상태(done/A1_extract)로 남는다 — 'failed'가 아님.
    assert row.status == "done"
    assert row.step == "A1_extract"


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
    assert got["summary"] == _SAMPLE_SUMMARY
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
