"""app/services/sllm_client.py 검증 — 요청 조립과 error 필드 처리만 확인한다(실제 네트워크
없음, url_guard.fetch를 mock).
"""

from __future__ import annotations

from unittest import mock

import pytest

from app.config import settings
from app.services.sllm_client import (
    SllmError,
    SllmNotConfiguredError,
    classify_doc,
    classify_topic,
    get_extract_requirements_status,
    start_extract_requirements,
)


@pytest.fixture(autouse=True)
def _sllm_configured():
    with mock.patch.object(settings, "sllm_base_url", "http://internal-sllm:8081"), \
         mock.patch.object(settings, "sllm_api_token", "test-token"):
        yield


def _fake_response(body: dict, status_code: int = 200):
    response = mock.Mock()
    response.json.return_value = body
    response.status_code = status_code
    return response


def test_classify_doc_not_configured_raises_explicitly():
    with mock.patch.object(settings, "sllm_base_url", ""):
        with pytest.raises(SllmNotConfiguredError):
            classify_doc("텍스트", trace_id="t1")


def test_classify_doc_sends_expected_request_and_parses_output():
    fake = _fake_response({"output": {"is_boilerplate": True, "reason": "제출서류 양식"}, "model": "qwen3-4b"})
    with mock.patch("app.services.sllm_client.fetch", return_value=fake) as mock_fetch:
        result = classify_doc("제출서류(양식) 안내", trace_id="notice_1")

    assert result["output"]["is_boilerplate"] is True
    call = mock_fetch.call_args
    assert call.args[0] == "http://internal-sllm:8081/v1/classify-doc"
    assert call.kwargs["json"] == {"input_text": "제출서류(양식) 안내", "trace_id": "notice_1"}
    assert call.kwargs["headers"] == {"Authorization": "Bearer test-token"}


def test_classify_topic_sends_topics_as_context():
    fake = _fake_response({"output": {"matches": [{"topic_id": 21, "confidence": 0.98, "reason": "..."}]}})
    topics = [{"topic_id": 21, "name": "로봇/자동화", "keywords": ["로봇"]}]
    with mock.patch("app.services.sllm_client.fetch", return_value=fake) as mock_fetch:
        result = classify_topic("자동화 설비 구축 사업", topics, trace_id="notice_2")

    assert result["output"]["matches"][0]["topic_id"] == 21
    assert mock_fetch.call_args.kwargs["json"] == {
        "input_text": "자동화 설비 구축 사업",
        "context": {"topics": topics},
        "trace_id": "notice_2",
    }


def test_start_extract_requirements_returns_job_id():
    # 2026-09-20 — 동기 단일 호출(청크 수에 비례해 수 분)에서 job 폴링 방식으로 재설계됨.
    fake = _fake_response({"job_id": "job-123", "status": "queued", "trace_id": "notice_3"}, status_code=202)
    with mock.patch("app.services.sllm_client.fetch", return_value=fake) as mock_fetch:
        result = start_extract_requirements("규격서 본문" * 1000, trace_id="notice_3")

    assert result["job_id"] == "job-123"
    call = mock_fetch.call_args
    assert call.args[0] == "http://internal-sllm:8081/v1/extract-requirements"
    assert call.kwargs["json"] == {"input_text": "규격서 본문" * 1000, "trace_id": "notice_3"}


def test_get_extract_requirements_status_polls_by_job_id():
    fake = _fake_response({
        "status": "done", "chunks_processed": 3, "chunks_total": 3,
        "output": {"requirements": [], "summary": {}},
    })
    with mock.patch("app.services.sllm_client.fetch", return_value=fake) as mock_fetch:
        result = get_extract_requirements_status("job-123")

    assert result["status"] == "done"
    call = mock_fetch.call_args
    assert call.args[0] == "http://internal-sllm:8081/v1/extract-requirements/job-123"
    assert call.kwargs["method"] == "GET"


def test_raises_sllm_error_when_response_has_error_field():
    fake = _fake_response({"error": {"code": "inference_failed", "message": "모델 응답 없음"}, "trace_id": "notice_4"})
    with mock.patch("app.services.sllm_client.fetch", return_value=fake):
        with pytest.raises(SllmError) as exc_info:
            classify_doc("텍스트", trace_id="notice_4")
    assert exc_info.value.code == "inference_failed"


def test_raises_sllm_error_on_http_failure_without_error_field():
    fake = _fake_response({}, status_code=502)
    with mock.patch("app.services.sllm_client.fetch", return_value=fake):
        with pytest.raises(SllmError) as exc_info:
            classify_doc("텍스트", trace_id="notice_5")
    assert exc_info.value.code == "http_error"


def test_raises_sllm_error_when_response_is_not_json():
    fake = mock.Mock()
    fake.json.side_effect = ValueError("no JSON")
    fake.status_code = 200
    with mock.patch("app.services.sllm_client.fetch", return_value=fake):
        with pytest.raises(SllmError) as exc_info:
            classify_doc("텍스트", trace_id="notice_6")
    assert exc_info.value.code == "malformed_output"
