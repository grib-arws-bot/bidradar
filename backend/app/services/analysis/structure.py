"""S8 A2 — 요구사양 구조화(LLM). CLAUDE.md 타협 불가 원칙 1번:

"LLM은 규격서에서 요구사양을 추출·정규화만 한다. 충족 여부는 match.py가 규칙으로
판정한다." 이 모듈은 절대 judgement/matched_product_id를 채우지 않는다 — LLM 응답에
그런 필드가 섞여 와도 무시하고 항상 analysis_requirement 테이블 기본값(unknown/NULL)
그대로 둔다. 판정은 이후 A3(match.py)의 몫이다.

원칙 2("판정은 권고, 근거 없는 판정은 화면에 안 낸다")에 따라 cite(조문 위치)가 없는
항목은 저장하지 않는다. 원칙 3("자동 실행 금지")은 이 함수를 호출하는 쪽(관리자 명시적
버튼 클릭 또는 CLI)의 책임 — 이 모듈 자체는 auto_extract 같은 자동 트리거에 절대
연결하지 않는다(비용 발생, 구현스펙 07절 "비용 때문에 자주 호출하지 말 것").
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from app.config import settings
from app.models import analysis, analysis_doc, analysis_requirement
from app.security.url_guard import fetch

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# 구현스펙 07절 "모델은 하드코딩 3종 중 관리자가 선택" — CLI·API가 공유하는 짧은 별칭.
MODEL_ALIASES = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-5",
}

# 100만 토큰당 USD — Anthropic 공식 가격표 기준 근사치(2026-09 확인). 요금이 바뀌면
# platform.claude.com 가격 페이지와 대조해 갱신할 것 — analysis.llm_cost는 정산용이 아니라
# 예산 감시용 근사값이다.
PRICING_PER_MTOK = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-opus-5": {"input": 15.00, "output": 75.00},
}

OPS = ("gte", "lte", "eq", "contains", "manual")

_MAX_DOC_CHARS = 120_000  # Haiku 컨텍스트(200k 토큰) 안에 여유 있게 들어오는 상한 — 넘으면 잘라내고 표시한다.

_CATEGORIES = ("성능", "인증", "실적", "인력", "기타")

_TOOL_NAME = "extract_requirements"
_SYSTEM_PROMPT = """당신은 공공입찰·정부지원 규격서를 관리자가 한눈에 읽을 수 있게 정리하는
보조 도구입니다. 두 가지를 만듭니다 — (1) 항목/값/연산자로 쪼갤 수 있는 개별 요구사양 목록,
(2) 항목으로 쪼개지지 않는 서술형 개요. 둘 다 판단이 아니라 추출·정리입니다.

공통 규칙:
- 문서에 실제로 명시된 내용만 씁니다 — 추측하거나 일반적인 상식으로 채우지 마세요.
- 충족 여부를 판단하지 마세요. judgement 같은 필드는 절대 포함하지 마세요.
- 찾을 수 없는 필드는 빈 문자열/빈 배열로 두세요 — 지어내지 마세요.

[requirements] 개별 요구사양(신청자격 제외 — 아래 eligibility에 따로 정리)
1. 각 항목은 반드시 원문 조문 위치(cite)를 함께 답니다 — 장/절/항 번호나 표 제목처럼 문서에서
   다시 찾을 수 있는 표현으로 적으세요. 위치를 특정할 수 없으면 그 항목은 아예 추출하지 마세요.
2. 수치 비교 가능한 항목(예: "3년 이상 유지보수 실적")은 op을 gte/lte/eq 중 하나로, req_value에
   숫자만, req_unit에 단위를 분리해서 넣으세요.
3. 특정 목록에 포함되는지 여부(예: 보유해야 할 인증 목록)는 op="contains"로 넣으세요.
4. 서술형이라 규칙으로 판정할 수 없는 항목(예: "제안서에 구축 방안을 상세히 기술할 것")은
   op="manual"로 넣고 req_value/req_unit은 비워두세요.
5. category는 성능/인증/실적/인력/기타 중 문서 맥락에 맞는 것으로 분류하세요.

[summary] 서술형 개요
- project_period: 사업(연구개발)기간. 예: "5년 이내(당해 9개월 이내)"
- project_budget: 사업금액(정부지원연구개발비 등). 예: "150억원 이내(당해 19억원)"
- purpose: 사업목적 — **원문 문장을 의역하지 말고 그대로 인용**하세요.
- sub_business: 세부사업(내역사업)명. 표에 "세부사업"·"내역사업"으로 표시된 경우가 많습니다.
- task_type: 과제유형 {execution_system(추진체계: 예 일반형/통합형/병렬형),
  development_form(개발형태: 예 원천기술형/혁신제품형), call_type(공모형태: 예 지정공모형/품목지정형)}.
  문서에 정의된 표현을 그대로 쓰세요. 과제마다 다르면 대표적인 값을 쓰고 다른 경우는 무시.
- contact: 문의처 {department(담당부서), role(직책/역할, 예: "OO PD"), phone(연락처),
  email(이메일)}. "문의처"·"담당" 섹션의 표나 문장에서 찾으세요.
- content_items: 사업내용을 **과제 단위로 나눠** 배열로 정리하세요(하나의 사업 안에 여러
  RFP/품목이 있으면 각각 별도 항목으로). 각 항목: {title(과제명/품목명), summary(개념·목표·
  개발내용을 관리자가 이해할 수 있게 종합 분석한 문단 — 원문 나열이 아니라 분석), period(그
  과제의 연구개발기간, 없으면 사업 전체 기간), budget(그 과제의 정부지원연구개발비, 없으면
  사업 전체 예산)}. 과제가 하나뿐이면 배열에 항목 하나만 넣으세요.
- evaluation: 평가기준을 {item, weight, note} 목록으로. item/weight/note 모두 **원문 표현을
  그대로** 옮기세요(재구성·의역 금지) — 배점표가 있으면 항목명·비율·세부 평가내용을 원문 그대로.
- budget_conditions: 사업비 조건(중소기업 기준). **모두 단답형으로 짧게** — 전체 문장이 아니라
  핵심 수치나 키워드만 씁니다:
    - government_support_ratio: 예: "75% 이하"
    - institution_cash_burden_ratio: 예: "10% 이상"
    - tech_fee_collection: 예: "징수대상" 또는 "미징수"
    - youth_hiring_requirement: 예: "5억원당 1명"
    - labor_cost_basis: 현금 계상이 허용되는 핵심 조건만 키워드로(예: "지식서비스 분야", "신규채용자")
- eligibility: 신청자격 {consortium(컨소시엄 요건), lead_org(주관기관 요건),
  participant_org(참여기관 요건), demand_org(수요기관 요건), company_size(기업규모 요건),
  special_notes(그 외 특이사항)}. **모두 단답형으로 짧게**(예: "산학연 컨소시엄 필수",
  "중소기업만 해당"). 동일기관 중복참여 불가·재무 부적격·참여제한·PM 발표 같은 모든 공고에
  공통적인 당연한 사항은 적지 마세요 — 이 공고에 특징적인 요건만 남기세요.
- submission: 제안제출 {deadline(제출기한), method(제출방법·사이트), documents(제출서류
  핵심만 요약, 표 전체를 옮기지 말 것)}.
- other_notes: 기타사항 — 특별한 성능·실적 요구나 위 항목에 안 들어가는 특이사항이 있으면
  1~3문장으로. 없으면 빈 문자열."""

_REQUIREMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": list(_CATEGORIES)},
                    "req_text": {"type": "string", "description": "요구사항 원문을 간결하게 정리한 문장"},
                    "req_value": {"type": "string", "description": "비교 가능한 값(없으면 빈 문자열)"},
                    "req_unit": {"type": "string", "description": "단위(없으면 빈 문자열)"},
                    "op": {"type": "string", "enum": list(OPS)},
                    "cite": {"type": "string", "description": "문서 내 조문 위치"},
                },
                "required": ["category", "req_text", "op", "cite"],
            },
        },
        "summary": {
            "type": "object",
            "properties": {
                "project_period": {"type": "string"},
                "project_budget": {"type": "string"},
                "purpose": {"type": "string"},
                "sub_business": {"type": "string"},
                "task_type": {
                    "type": "object",
                    "properties": {
                        "execution_system": {"type": "string"},
                        "development_form": {"type": "string"},
                        "call_type": {"type": "string"},
                    },
                    "required": ["execution_system", "development_form", "call_type"],
                },
                "contact": {
                    "type": "object",
                    "properties": {
                        "department": {"type": "string"},
                        "role": {"type": "string"},
                        "phone": {"type": "string"},
                        "email": {"type": "string"},
                    },
                    "required": ["department", "role", "phone", "email"],
                },
                "content_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "summary": {"type": "string"},
                            "period": {"type": "string"},
                            "budget": {"type": "string"},
                        },
                        "required": ["title", "summary", "period", "budget"],
                    },
                },
                "evaluation": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item": {"type": "string"},
                            "weight": {"type": "string"},
                            "note": {"type": "string"},
                        },
                        "required": ["item", "weight"],
                    },
                },
                "budget_conditions": {
                    "type": "object",
                    "properties": {
                        "government_support_ratio": {"type": "string"},
                        "institution_cash_burden_ratio": {"type": "string"},
                        "tech_fee_collection": {"type": "string"},
                        "youth_hiring_requirement": {"type": "string"},
                        "labor_cost_basis": {"type": "string"},
                    },
                    "required": [
                        "government_support_ratio", "institution_cash_burden_ratio", "tech_fee_collection",
                        "youth_hiring_requirement", "labor_cost_basis",
                    ],
                },
                "eligibility": {
                    "type": "object",
                    "properties": {
                        "consortium": {"type": "string"},
                        "lead_org": {"type": "string"},
                        "participant_org": {"type": "string"},
                        "demand_org": {"type": "string"},
                        "company_size": {"type": "string"},
                        "special_notes": {"type": "string"},
                    },
                    "required": ["consortium", "lead_org", "participant_org", "demand_org", "company_size", "special_notes"],
                },
                "submission": {
                    "type": "object",
                    "properties": {
                        "deadline": {"type": "string"},
                        "method": {"type": "string"},
                        "documents": {"type": "string"},
                    },
                    "required": ["deadline", "method", "documents"],
                },
                "other_notes": {"type": "string"},
            },
            "required": [
                "project_period", "project_budget", "purpose", "sub_business", "task_type", "contact",
                "content_items", "evaluation", "budget_conditions", "eligibility", "submission", "other_notes",
            ],
        },
    },
    "required": ["requirements", "summary"],
}


class LLMNotConfiguredError(Exception):
    """ANTHROPIC_API_KEY가 설정되지 않음 — 조용히 건너뛰지 않고 명시적으로 거부한다."""


class StructuringInProgressError(Exception):
    """이 analysis는 이미 A2 구조화가 완료됨 — 중복 LLM 호출(비용) 방지."""


def _collect_source_text(conn: Connection, analysis_id: int) -> str:
    docs = conn.execute(
        select(analysis_doc.c.name, analysis_doc.c.text)
        .where(analysis_doc.c.analysis_id == analysis_id, analysis_doc.c.extract_ok.is_(True))
        .order_by(analysis_doc.c.id)
    ).all()
    parts = [f"=== {name} ===\n{text}" for name, text in docs if text]
    combined = "\n\n".join(parts)
    if len(combined) > _MAX_DOC_CHARS:
        combined = combined[:_MAX_DOC_CHARS] + "\n\n[문서가 길어 이후 내용은 잘렸습니다]"
    return combined


def _call_anthropic(model: str, document_text: str) -> tuple[list[dict], dict, int, int]:
    """(requirements, summary, input_tokens, output_tokens)를 반환한다. HTTP 호출 자체가
    실패하면 그대로 예외를 던진다 — 실패해도 흔적 없이 사라지면 안 되므로 호출부가
    analysis.status를 반드시 갱신해야 한다."""
    payload = {
        "model": model,
        "max_tokens": 16000,  # 2026-09-05 — 과제별 content_items·문의처·신청자격 등 필드가 늘어 8000으로는 부족한 사례 발견
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": f"다음은 공공입찰 규격서 원문입니다.\n\n{document_text}"}],
        "tools": [
            {
                "name": _TOOL_NAME,
                "description": "규격서에서 추출한 요구사양 목록을 구조화된 형태로 반환합니다.",
                "input_schema": _REQUIREMENT_SCHEMA,
            }
        ],
        "tool_choice": {"type": "tool", "name": _TOOL_NAME},
    }
    response = fetch(
        ANTHROPIC_MESSAGES_URL,
        method="POST",
        timeout=180,
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
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    tool_use = next((block for block in body.get("content", []) if block.get("type") == "tool_use"), None)
    if tool_use is None:
        raise RuntimeError("모델이 구조화된 형식으로 응답하지 않았습니다(tool_use 블록 없음)")

    tool_input = tool_use.get("input", {})
    requirements = tool_input.get("requirements", [])
    summary = tool_input.get("summary", {})
    return requirements, summary, input_tokens, output_tokens


def _valid_items(raw_items: list[dict]) -> tuple[list[dict], int]:
    """cite 없는 항목은 근거 없는 추출이라 버린다(원칙 2). (유효 항목, 버린 개수)."""
    valid, skipped = [], 0
    for item in raw_items:
        category = (item.get("category") or "").strip()
        req_text = (item.get("req_text") or "").strip()
        op = item.get("op")
        cite = (item.get("cite") or "").strip()
        if not (category and req_text and cite and op in OPS):
            skipped += 1
            continue
        valid.append(
            {
                "category": category,
                "req_text": req_text,
                "req_value": (item.get("req_value") or "").strip() or None,
                "req_unit": (item.get("req_unit") or "").strip() or None,
                "op": op,
                "cite": cite,
            }
        )
    return valid, skipped


def run_structuring(conn: Connection, analysis_id: int, *, model: str = "claude-haiku-4-5-20251001") -> dict:
    """A2 — analysis_doc에 이미 추출된 텍스트(A1 결과)를 LLM으로 구조화해 analysis_requirement에
    쌓는다. 반환값은 요약(로그·테스트 검증용)."""
    if not settings.anthropic_api_key:
        raise LLMNotConfiguredError("ANTHROPIC_API_KEY가 설정되지 않았습니다 — infra/.env에 추가한 뒤 재기동하세요.")
    if model not in PRICING_PER_MTOK:
        raise ValueError(f"허용되지 않은 모델: {model} (허용: {', '.join(PRICING_PER_MTOK)})")

    row = conn.execute(select(analysis.c.notice_id).where(analysis.c.id == analysis_id)).first()
    if row is None:
        raise ValueError(f"분석을 찾을 수 없습니다: {analysis_id}")

    already = conn.execute(
        select(analysis_requirement.c.id).where(analysis_requirement.c.analysis_id == analysis_id).limit(1)
    ).first()
    if already:
        raise StructuringInProgressError(f"analysis id={analysis_id}는 이미 A2 구조화가 완료됐습니다 — 재실행하려면 새로 분석하세요.")

    document_text = _collect_source_text(conn, analysis_id)
    if not document_text:
        raise ValueError("추출된 문서 텍스트가 없어 구조화를 진행할 수 없습니다(A1이 먼저 성공해야 함).")

    conn.execute(
        analysis.update().where(analysis.c.id == analysis_id).values(status="running", step="A2_structure")
    )

    try:
        raw_items, summary, input_tokens, output_tokens = _call_anthropic(model, document_text)
    except Exception as exc:  # noqa: BLE001 — 실패도 반드시 기록(CLAUDE.md "조용한 실패 금지")
        conn.execute(
            analysis.update()
            .where(analysis.c.id == analysis_id)
            .values(status="failed", step="A2_structure", finished_at=datetime.now(timezone.utc), verdict=str(exc))
        )
        raise

    cost = (input_tokens / 1_000_000) * PRICING_PER_MTOK[model]["input"] + (
        output_tokens / 1_000_000
    ) * PRICING_PER_MTOK[model]["output"]

    valid_items, skipped = _valid_items(raw_items)
    for item in valid_items:
        conn.execute(insert(analysis_requirement).values(analysis_id=analysis_id, **item))

    conn.execute(
        analysis.update()
        .where(analysis.c.id == analysis_id)
        .values(
            status="done",
            step="A2_structure",
            finished_at=datetime.now(timezone.utc),
            llm_tokens=analysis.c.llm_tokens + input_tokens + output_tokens,
            llm_cost=analysis.c.llm_cost + cost,
            summary=summary or None,
        )
    )

    return {
        "analysis_id": analysis_id,
        "extracted": len(raw_items),
        "saved": len(valid_items),
        "skipped_no_cite": skipped,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 4),
    }


def _latest_analysis_id(conn: Connection, notice_id: int) -> int | None:
    return conn.execute(
        select(analysis.c.id).where(analysis.c.notice_id == notice_id).order_by(analysis.c.ver.desc())
    ).scalars().first()


def run_structuring_for_notice(conn: Connection, notice_id: int, *, model: str = "claude-haiku-4-5-20251001") -> dict:
    """공고 상세 화면(관리자가 버튼을 눌러 실행)에서 쓰는 진입점 — 그 공고의 가장 최근 분석
    (A1이 이미 끝나 있어야 함)에 대해 A2를 실행한다."""
    analysis_id = _latest_analysis_id(conn, notice_id)
    if analysis_id is None:
        raise ValueError("먼저 첨부문서 추출(A1)을 실행해야 합니다 — 진행된 분석이 없습니다.")
    return run_structuring(conn, analysis_id, model=model)


def get_requirements(conn: Connection, notice_id: int) -> dict | None:
    """공고 상세 화면 조회용 — 가장 최근 분석의 요구사양 목록. judgement/matched_product_id는
    A2 단계에선 의미 없는 값(항상 unknown/NULL)이라 화면에 혼동을 주지 않도록 응답에서 뺀다
    (A3가 실제 판정을 붙이기 전까지)."""
    row = conn.execute(
        select(analysis.c.id, analysis.c.status, analysis.c.step, analysis.c.summary)
        .where(analysis.c.notice_id == notice_id)
        .order_by(analysis.c.ver.desc())
    ).first()
    if row is None:
        return None

    reqs = conn.execute(
        select(
            analysis_requirement.c.category,
            analysis_requirement.c.req_text,
            analysis_requirement.c.req_value,
            analysis_requirement.c.req_unit,
            analysis_requirement.c.op,
            analysis_requirement.c.cite,
        )
        .where(analysis_requirement.c.analysis_id == row.id)
        .order_by(analysis_requirement.c.id)
    ).mappings().all()

    return {
        "analysis_id": row.id,
        "status": row.status,
        "step": row.step,
        "summary": row.summary,
        "requirements": [dict(r) for r in reqs],
    }
