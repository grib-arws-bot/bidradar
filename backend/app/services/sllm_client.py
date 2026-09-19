"""사내 sLLM(Qwen3-4B, 자체 호스팅, thingx.grib-iot.com:28081) 호출 클라이언트(2026-09-20,
의사결정_로그 175번).

세 엔드포인트를 얇게 감싼다 — 판정·정규화 로직은 여기 안 둔다(그건 이 파일을 부르는
쪽이나 app/services/sllm_verification.py의 몫). 이 모듈의 책임은 요청 조립 + 응답의
error 필드 확인뿐이다.

모든 외부 HTTP 요청은 url_guard를 거친다(CLAUDE.md, 예외 없음). sLLM 서버는 BidRadar
자체 prod 서버와 같은 호스트(thingx.grib-iot.com, 공인 IP 1.220.120.74)라 url_guard의
SSRF 차단 대역(사설 IP)과는 무관 — 다만 28081이 표준 포트가 아니라서 url_guard의
ALLOWED_PORTS에 추가해야 했다(9443 선례와 동일 패턴, app/security/url_guard.py 참고).

A(요구사항 추출)는 청크 수에 비례해 오래 걸릴 수 있어 동기 호출이 아니라 job 폴링
방식이다(2026-09-20 — 처음엔 동기 단일 호출이었으나 GPU 전환 후에도 "상세페이지 열자마자
즉시 미리보기"에는 안 맞는다고 판단해 sLLM팀이 비동기로 재설계) — start_extract_requirements()로
접수하고 get_extract_requirements_status()로 폴링한다.
"""

from __future__ import annotations

from app.config import settings
from app.security.url_guard import fetch

# C/B/A 접수·폴링 전부 짧게 끝난다(A도 job 접수 자체는 즉시 202 반환, 폴링 한 번도
# 가벼운 상태 조회일 뿐이라 실제 추출 작업 시간과 무관) — 공통으로 넉넉한 여유만 둔다.
_DEFAULT_TIMEOUT_SECONDS = 60


class SllmNotConfiguredError(Exception):
    """SLLM_BASE_URL 또는 SLLM_API_TOKEN이 설정되지 않음 — 조용히 건너뛰지 않고 명시적으로
    거부한다(CLAUDE.md 조용한 실패 금지)."""


class SllmError(Exception):
    """sLLM이 명시적으로 반환한 오류(unauthorized/empty_input/inference_failed/
    malformed_output 등) 또는 응답 형식 자체가 계약과 다른 경우."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _request(method: str, path: str, *, json: dict | None = None) -> dict:
    if not settings.sllm_base_url or not settings.sllm_api_token:
        raise SllmNotConfiguredError(
            "SLLM_BASE_URL/SLLM_API_TOKEN이 설정되지 않았습니다 — infra/.env에 추가한 뒤 재기동하세요."
        )
    url = f"{settings.sllm_base_url.rstrip('/')}{path}"
    kwargs: dict = {"headers": {"Authorization": f"Bearer {settings.sllm_api_token}"}, "timeout": _DEFAULT_TIMEOUT_SECONDS}
    if json is not None:
        kwargs["json"] = json
    response = fetch(url, method=method, **kwargs)

    try:
        body = response.json()
    except ValueError as exc:
        raise SllmError("malformed_output", f"응답이 JSON이 아님(HTTP {response.status_code})") from exc

    if "error" in body:
        error = body["error"]
        raise SllmError(error.get("code", "unknown"), error.get("message", ""))
    if response.status_code >= 400:
        raise SllmError("http_error", f"HTTP {response.status_code}, 응답에 error 필드 없음")
    return body


def classify_doc(text: str, *, trace_id: str) -> dict:
    """첨부문서 앞부분(500~1,000자)이 공통 문서(제출서류·규정·양식 등)인지 분류한다.
    응답 output 형식: {"is_boilerplate": bool, "reason": str}."""
    return _request("POST", "/v1/classify-doc", json={"input_text": text, "trace_id": trace_id})


def classify_topic(title: str, topics: list[dict], *, trace_id: str) -> dict:
    """공고 제목과 활성 관심주제 목록을 넣어 의미상 관련 주제를 찾는다. topics는
    [{"topic_id": int, "name": str, "keywords": [str]}] 형태. 응답 output 형식:
    {"matches": [{"topic_id": int, "confidence": float, "reason": str}]} — confidence는
    자동 판정에 쓰지 않고 사람 검토 후보로만 쓴다(sLLM팀과 합의된 원칙)."""
    return _request(
        "POST",
        "/v1/classify-topic",
        json={"input_text": title, "context": {"topics": topics}, "trace_id": trace_id},
    )


def start_extract_requirements(text: str, *, trace_id: str) -> dict:
    """규격서 원문(길이 제한 없음 — 서버가 2,500자 단위로 청킹)에서 요구사항 추출 작업을
    접수한다. 즉시 {"job_id", "status": "queued", "trace_id"}를 반환 — 결과는 동기로 안
    돌아온다. get_extract_requirements_status(job_id)로 폴링해야 한다."""
    return _request("POST", "/v1/extract-requirements", json={"input_text": text, "trace_id": trace_id})


def get_extract_requirements_status(job_id: str) -> dict:
    """추출 작업 상태를 폴링한다. status가 "done"이면 output(requirements/summary)이
    채워진다 — 그대로 쓰지 말고 반드시 app.services.sllm_verification.sanitize_sllm_requirements()
    로 근거 검증·청크 중복 제거를 거친 뒤 사용한다(원문에 없는 토큰이 인용문에 섞이는 현상이
    실측됨, 아직 미해결 — 계속 관찰 중)."""
    return _request("GET", f"/v1/extract-requirements/{job_id}")
