"""고객 프로필 요약(2026-09-05, "Phase 1" 보고서 최적화 설계) — 고객이 올린 소개서
(customer_document)와 참고 URL(customer.reference_urls, 2026-09-11 추가)을 매 보고서
생성마다 LLM에 다시 넣는 대신, 한 번 요약해 MD로 캐싱해둔다(사용자 확정 — 비용 절감·검증
가능성). 소개서를 새로 올리거나 바꿔도 자동 재요약하지 않는다 — 관리자가 버튼을 눌러야만
실행한다("고객사 AI 재분석은 관리자가 수동으로", CLAUDE.md 원칙 3 "자동 실행 금지"와 같은 이유).

기본 모델은 Sonnet — 이 요약이 이후 모든 보고서 코멘트 생성의 기반 자료가 되므로(1회성·저빈도
호출이라 비용 부담도 작음) Haiku보다 품질을 우선한다.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from app.config import settings
from app.models import customer, customer_document
from app.security.url_guard import fetch
from app.services.customer_interest import (
    TOPIC_PRIORITIES,
    InterestDraft,
    draft_from_profile,
    get_interest_profile,
    get_topic_catalog,
    save_interest_profile,
)
from app.services.document_extract import extract_document
from app.services.html_text import extract_text_and_links

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# structure.py와 같은 별칭·가격표(2곳뿐이라 공용 모듈로 뺄 정도는 아님) — 가격이 바뀌면 양쪽 다 갱신.
MODEL_ALIASES = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-5",
}
PRICING_PER_MTOK = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-opus-5": {"input": 15.00, "output": 75.00},
}

_MAX_DOC_CHARS = 60_000  # 소개서는 규격서(structure.py 120,000)보다 대체로 짧음

_SYSTEM_PROMPT = """당신은 영업 지원 도구입니다. 회사가 올린 소개서(회사소개서·제품소개서 등)
원문을 읽고, 이후 공공입찰·정부지원 공고 추천과 고객 전략 수립에 참고할 프로필을 한국어
마크다운으로 정리하세요.

**개조식으로 쓰세요** — "~다/~습니다"로 끝나는 완결된 문장이 아니라, "~함", "~보유", "~중심"
처럼 명사형·용언 어간으로 끝나는 짧은 불릿(`- `)으로 씁니다. 불릿 하나는 한 문장 분량을
넘기지 마세요.

다음 섹션을 포함하세요:
## 회사 개요
## 주요 제품/서비스
## 핵심 기술/차별화 포인트
## 주요 고객/실적
## 타겟 시장/분야

원문에 실제로 있는 내용만 쓰세요 — 지어내지 마세요. 섹션에 해당하는 원문 근거가 없으면
"- 정보 없음"이라고 쓰세요. 관리자가 이후 직접 다듬을 수 있으므로 과도하게 길게 쓰지 말고
핵심만 담으세요."""

# 관심주제 자동 설정(2026-09-11 사용자 지시) — 프로필 요약이 처음 만들어질 때(관심주제가
# 하나도 선택 안 돼 있을 때만, 관리자가 이미 고른 게 있으면 절대 안 건드림) 회사 프로필을
# 보고 어울리는 관심주제를 미리 골라준다. 완전한 판정이 아니라 "출발점" 제공이라 관리자가
# 언제든 관심주제 화면에서 그대로 고쳐 쓸 수 있다.
_TOPIC_CLASSIFY_SYSTEM_PROMPT = """당신은 공공입찰 플랫폼의 고객 온보딩 도우미입니다. 회사
프로필을 읽고, 주어진 관심주제 목록 중 이 회사의 사업과 실제로 관련 있는 것만 고르세요.

규칙:
- 목록에 있는 topic_id만 쓰세요. 목록에 없는 주제를 지어내지 마세요.
- 근거가 약하면 포함하지 마세요 — 관련 없는 주제를 너무 많이 고르면 나중에 엉뚱한 공고가
  추천됩니다. 보통 2~6개가 적당합니다.
- priority는 그 회사의 핵심 사업이면 "high", 관련은 있지만 핵심은 아니면 "normal", 부차적
  관심사면 "low"로 주세요.
- 다른 설명 없이 JSON 배열만 출력하세요. 형식: [{"topic_id": 1, "priority": "high"}, ...]
  관련 주제가 하나도 없으면 빈 배열 []을 출력하세요."""


class NoDocumentsError(Exception):
    """추출 가능한 소개서 파일도, 읽어올 수 있는 참고 URL도 없음 — 먼저 하나는 등록해야 함."""


class LLMNotConfiguredError(Exception):
    pass


def _collect_document_text(conn: Connection, customer_id: int) -> str:
    rows = conn.execute(
        select(customer_document.c.filename, customer_document.c.content).where(
            customer_document.c.customer_id == customer_id
        )
    ).all()
    parts = []
    for filename, content in rows:
        result = extract_document(filename, content)
        if result.ok and result.text:
            parts.append(f"=== {filename} ===\n{result.text}")
    return "\n\n".join(parts)


_URL_FETCH_TIMEOUT_SECONDS = 30

# 참고 URL 하나를 주면 같은 도메인 안의 페이지를 재귀적으로 따라가며 함께 분석한다
# (2026-09-11 사용자 지시) — 무한 크롤링을 막기 위한 안전장치 2단(analysis_pilot.py의
# 중첩 zip 깊이 제한과 같은 취지): 깊이 상한 + 총 페이지 수 상한.
_MAX_CRAWL_DEPTH = 2
_MAX_CRAWL_PAGES = 30
_MAX_FAILED_URLS_REPORTED = 10

# 게시판·게시글 목록처럼 페이지네이션이 끝없이 이어질 수 있는 URL은 그 페이지 본문은
# 가져오되(사용자가 직접 지정했을 수도 있음) 그 안의 링크는 더 따라가지 않는다 — "게시판
# 같은 경우에는 더 깊이 들어가지 않아도 된다"(2026-09-11 사용자 지시). 완벽한 판별은
# 불가능하니 흔한 게시판 URL 패턴 + 위 깊이·페이지 수 상한을 함께 안전장치로 둔다.
_BOARD_LIKE_URL_PATTERN = re.compile(r"(board|bbs|notice|news|article|list)", re.IGNORECASE)


def _is_board_like(url: str) -> bool:
    parsed = urlparse(url)
    return bool(_BOARD_LIKE_URL_PATTERN.search(parsed.path)) or bool(_BOARD_LIKE_URL_PATTERN.search(parsed.query))


def _fetch_page_text_and_links(url: str) -> tuple[str | None, list[str], str | None]:
    """(본문, 이 페이지에서 찾은 링크 목록, 실패 사유). 본문을 못 구했으면 첫 번째 값이 None."""
    try:
        response = fetch(url, timeout=_URL_FETCH_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 — SSRF 차단·타임아웃·연결 실패 등 원인이 다양해 전부 "이 URL 실패"로 처리
        return None, [], str(exc)
    content_type = response.headers.get("content-type", "")
    if content_type and "html" not in content_type:
        text = response.text
        return (text if text.strip() else None), [], (None if text.strip() else "본문을 찾지 못했습니다")
    text, links = extract_text_and_links(response.text)
    return (text if text.strip() else None), links, (None if text.strip() else "본문을 찾지 못했습니다")


def _collect_url_text(reference_urls: list[str]) -> tuple[str, list[str]]:
    """참고 URL마다 같은 도메인 안의 링크를 BFS로 따라가며 본문을 모은다. 실패한 URL은
    조용히 건너뛰지 않고 failed로 보고한다(CLAUDE.md "조용한 빈 결과 금지") — 다만 크롤링
    특성상 죽은 링크가 많을 수 있어 보고 개수는 상한을 둔다."""
    parts: list[str] = []
    failed: list[str] = []
    visited: set[str] = set()
    queue: list[tuple[str, int, str]] = [(url, 0, urlparse(url).netloc) for url in reference_urls]

    while queue and len(visited) < _MAX_CRAWL_PAGES:
        url, depth, domain = queue.pop(0)
        normalized = url.split("#")[0]
        if normalized in visited:
            continue
        visited.add(normalized)

        text, links, error = _fetch_page_text_and_links(normalized)
        if text:
            parts.append(f"=== {normalized} ===\n{text}")
        elif len(failed) < _MAX_FAILED_URLS_REPORTED:
            failed.append(f"{normalized} ({error})")

        if depth >= _MAX_CRAWL_DEPTH or _is_board_like(normalized):
            continue
        for href in links:
            absolute = urljoin(normalized, href).split("#")[0]
            parsed = urlparse(absolute)
            if parsed.scheme in ("http", "https") and parsed.netloc == domain and absolute not in visited:
                queue.append((absolute, depth + 1, domain))

    return "\n\n".join(parts), failed


def _call_anthropic(*, model: str, system_prompt: str, user_content: str, max_tokens: int) -> tuple[str, int, int]:
    """공용 Anthropic 호출 — summarize_customer_profile(프로필 요약)과
    _classify_interest_topics(관심주제 자동 설정)가 함께 쓴다. (응답 텍스트, input_tokens,
    output_tokens)를 반환한다."""
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
    }
    response = fetch(
        ANTHROPIC_MESSAGES_URL,
        method="POST",
        timeout=120,
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    body = response.json()
    if "error" in body:
        raise RuntimeError(f"Anthropic API 오류: {body['error'].get('message', body['error'])}")

    usage = body.get("usage", {})
    text_block = next((b for b in body.get("content", []) if b.get("type") == "text"), None)
    if text_block is None:
        raise RuntimeError("모델이 텍스트로 응답하지 않았습니다.")
    return text_block["text"], usage.get("input_tokens", 0), usage.get("output_tokens", 0)


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000) * PRICING_PER_MTOK[model]["input"] + (
        output_tokens / 1_000_000
    ) * PRICING_PER_MTOK[model]["output"]


def _classify_interest_topics(
    conn: Connection, customer_id: int, summary_md: str, *, model: str
) -> tuple[list[str], int, int]:
    """프로필 요약 내용을 보고 관심주제 카탈로그 중 어울리는 것을 골라 저장한다. 호출부
    (summarize_customer_profile)가 "관심주제가 하나도 없을 때만" 부르므로 여기선 그 조건을
    다시 확인하지 않는다. 반환값은 (자동 선택된 주제 이름 목록, input_tokens, output_tokens)
    — 하나도 못 고르거나 파싱에 실패해도 예외를 던지지 않는다(부가 기능이 본 요약을 막으면
    안 됨), 대신 빈 목록을 반환한다."""
    catalog = get_topic_catalog(conn)
    if not catalog:
        return [], 0, 0

    catalog_text = "\n".join(f"- topic_id={t['id']}: {t['name']}" for t in catalog)
    user_content = f"관심주제 목록:\n{catalog_text}\n\n회사 프로필:\n{summary_md}"
    try:
        raw_text, input_tokens, output_tokens = _call_anthropic(
            model=model, system_prompt=_TOPIC_CLASSIFY_SYSTEM_PROMPT, user_content=user_content, max_tokens=1000
        )
        picks = json.loads(raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
    except Exception:  # noqa: BLE001 — 부가 기능 실패가 본 요약 자체를 막으면 안 됨(사용자가 관심주제 화면에서 언제든 수동 설정 가능)
        return [], 0, 0

    catalog_ids = {t["id"] for t in catalog}
    catalog_names = {t["id"]: t["name"] for t in catalog}
    topic_ids: list[int] = []
    topic_priorities: dict[int, str] = {}
    for pick in picks if isinstance(picks, list) else []:
        topic_id = pick.get("topic_id") if isinstance(pick, dict) else None
        priority = pick.get("priority", "normal") if isinstance(pick, dict) else "normal"
        if topic_id in catalog_ids and priority in TOPIC_PRIORITIES:
            topic_ids.append(topic_id)
            topic_priorities[topic_id] = priority

    if not topic_ids:
        return [], input_tokens, output_tokens

    # 관심주제만 채우고 기존 검색어·팔로우 기관·금액 하한은 그대로 둔다(전체 치환 함수라
    # 빈 draft로 부르면 다른 필드까지 지워짐).
    draft = draft_from_profile(get_interest_profile(conn, customer_id))
    draft.topic_ids = topic_ids
    draft.topic_priorities = topic_priorities
    save_interest_profile(conn, customer_id, draft)

    return [catalog_names[t] for t in topic_ids], input_tokens, output_tokens


def summarize_customer_profile(conn: Connection, customer_id: int, *, model: str = "claude-sonnet-5") -> dict:
    """관리자가 명시적으로 호출할 때만 실행(자동 실행 금지) — 소개서 원문을 요약해
    customer.profile_summary_md에 저장한다. 반환값은 요약+비용(로그·화면 표시용)."""
    if not settings.anthropic_api_key:
        raise LLMNotConfiguredError("ANTHROPIC_API_KEY가 설정되지 않았습니다 — infra/.env에 추가한 뒤 재기동하세요.")
    if model not in PRICING_PER_MTOK:
        raise ValueError(f"허용되지 않은 모델: {model} (허용: {', '.join(PRICING_PER_MTOK)})")

    reference_urls = (
        conn.execute(select(customer.c.reference_urls).where(customer.c.id == customer_id)).scalar_one() or []
    )
    document_text = _collect_document_text(conn, customer_id)
    url_text, failed_urls = _collect_url_text(reference_urls)
    combined_text = "\n\n".join(t for t in (document_text, url_text) if t)
    if not combined_text:
        raise NoDocumentsError("추출 가능한 소개서 파일도 읽어올 수 있는 참고 URL도 없습니다 — 먼저 하나는 등록하세요.")
    if len(combined_text) > _MAX_DOC_CHARS:
        combined_text = combined_text[:_MAX_DOC_CHARS] + "\n\n[내용이 길어 이후는 잘렸습니다]"

    summary_md, input_tokens, output_tokens = _call_anthropic(
        model=model,
        system_prompt=_SYSTEM_PROMPT,
        user_content=f"다음은 회사 소개서·참고 자료 원문입니다.\n\n{combined_text}",
        max_tokens=4000,
    )
    cost = _cost_usd(model, input_tokens, output_tokens)

    # 관심주제 자동 설정(2026-09-11) — 하나도 선택 안 돼 있을 때만. 관리자가 이미 고른 게
    # 있으면 재요약해도 절대 덮어쓰지 않는다(사용자 지시).
    auto_set_topics: list[str] = []
    if not get_interest_profile(conn, customer_id)["topic_ids"]:
        topic_names, classify_in, classify_out = _classify_interest_topics(conn, customer_id, summary_md, model=model)
        if topic_names:
            auto_set_topics = topic_names
            input_tokens += classify_in
            output_tokens += classify_out
            cost += _cost_usd(model, classify_in, classify_out)

    conn.execute(
        update(customer)
        .where(customer.c.id == customer_id)
        .values(
            profile_summary_md=summary_md,
            profile_summarized_at=datetime.now(timezone.utc),
            profile_summary_tokens=customer.c.profile_summary_tokens + input_tokens + output_tokens,
            profile_summary_cost=customer.c.profile_summary_cost + cost,
        )
    )

    return {
        "summary_md": summary_md,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 4),
        "failed_urls": failed_urls,
        "auto_set_topics": auto_set_topics,
    }


def save_manual_profile_summary(conn: Connection, customer_id: int, summary_md: str) -> None:
    """관리자가 AI 요약을 직접 손질할 때(개조식 다듬기·오탈자 수정 등) — LLM을 다시 부르지
    않고 텍스트만 갱신한다. profile_summarized_at("마지막 AI 생성 시각")은 건드리지 않는다 —
    수동 편집은 새로운 AI 생성이 아니므로."""
    conn.execute(update(customer).where(customer.c.id == customer_id).values(profile_summary_md=summary_md))
