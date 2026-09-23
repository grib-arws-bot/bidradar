"""공고별 "AI 사업 추진 전략"(2026-09-05) — 공개 리포트에서 고객이 공고를 클릭해 들어가면
보는 페이지. 미리 만들어두지 않고 고객이 처음 열 때만 생성한다 — (customer_id, notice_id)
유니크 제약 + INSERT ... ON CONFLICT DO NOTHING을 원자적 "선점" 수단으로 써서, 여러 번
눌러도 LLM 호출은 한 번만 일어난다.

생성 전에 그 공고의 첨부문서 자동분석(A1)·AI분석(A2)이 아직 안 됐으면 먼저 실행한다(사용자
지시) — 그래야 전략이 공고 원문 요구사항에 근거할 수 있다. 각각 실패해도(추출 불가 사이트,
파싱 실패 등) 전략 생성 자체는 있는 정보만으로 계속 진행한다(조용히 막지 않되, 못 구한 건
못 구한 대로 진행).

고객 단위(customer_id)로 캐싱하는 이유: 같은 공고가 여러 주의 리포트에 반복 등장할 수
있는데, 그때마다 다시 생성하면 낭비이고 내용도 어느 리포트에서 왔는지와 무관하게 고객+공고
조합에만 의존하기 때문.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection

from app.config import settings
from app.db import engine
from app.models import analysis, customer, notice, notice_strategy, org, source
from app.security.url_guard import fetch
from app.services.analysis.structure import run_structuring_for_notice
from app.services.analysis_pilot import AnalysisInProgressError, UnsupportedSourceError, run_extraction_pilot
from app.services.notice_classification import notice_status_label, notice_type_of, work_type_label
from app.services.notice_engagement import get_like_state
from app.services.notice_query import compute_bid_status

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5"  # 고객에게 그대로 노출되는 분석 문서라 품질 우선(Haiku 아님)

# customer_profile.py·report_commentary.py와 같은 가격표(3곳뿐이라 공용 모듈로 뺄 정도는 아님).
PRICING_PER_MTOK = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-opus-5": {"input": 15.00, "output": 75.00},
}

_SYSTEM_PROMPT = """당신은 영업 지원 도구입니다. 아래 공공입찰·정부지원 공고 정보(및 이미
추출됐다면 요구사항 요약)와 이 회사의 프로필을 보고, 이 공고에 실제로 참여할지 검토하는 데
도움이 되는 "사업 추진 전략"을 한국어 마크다운으로 작성하세요.

다음 섹션을 포함하세요:
## 공고 핵심 요약
## 이 회사에 적합한 이유
## 참여 시 준비해야 할 것
## 유의해야 할 리스크

- 공고 정보와 회사 프로필에 실제로 있는 내용에 근거하세요 — 지어내지 마세요.
- 회사 프로필이 없으면 공고 정보만으로 일반적인 관점에서 작성하고, 그 사실을 "이 회사에
  적합한 이유" 섹션 첫 줄에 명시하세요.
- 이 문서는 참여 여부를 최종 결정해주는 게 아니라 검토를 돕는 참고자료입니다 — "반드시
  참여해야 함"처럼 단정적으로 말하지 말고 "검토해볼 만함"처럼 권고 톤을 유지하세요."""


class LLMNotConfiguredError(Exception):
    pass


class NoticeNotFoundError(Exception):
    pass


def get_public_notice_summary(conn: Connection, notice_id: int, *, customer_id: int | None = None) -> dict | None:
    """공개(비로그인) 공고 상세용 — 내부 전용 필드(담당자 배정·그립 자신 팔로우 여부·
    자사 제품 충족판정 등)는 전부 뺀 고객 노출 안전 버전.

    customer_id를 주면 "AI 사업 추진 전략"이 이 (고객, 공고) 조합으로 이미 생성돼 있는지도
    같이 확인해 strategy 필드에 담는다(2026-09-12 — 이미 생성된 걸 다시 "생성" 버튼으로
    보여주면 사용자가 헷갈려한다는 지적). 생성만 트리거하지 않고 조회만 한다 — LLM 호출
    없음."""
    row = conn.execute(
        select(
            notice.c.id,
            notice.c.notice_no,
            notice.c.title,
            notice.c.stage,
            notice.c.est_price,
            notice.c.region,
            notice.c.biz_type,
            notice.c.open_dt,
            notice.c.close_dt,
            notice.c.url,
            org.c.name.label("org_name"),
            source.c.channel_name,
        )
        .select_from(notice)
        .join(org, org.c.id == notice.c.org_id, isouter=True)
        .join(source, source.c.id == notice.c.source_id, isouter=True)
        .where(notice.c.id == notice_id)
    ).mappings().first()
    if row is None:
        return None

    bid_status = compute_bid_status(row["open_dt"], row["close_dt"], datetime.now(timezone.utc))
    notice_type = notice_type_of(row["channel_name"])

    result = dict(row)
    result.pop("channel_name", None)
    result["est_price"] = int(result["est_price"]) if result["est_price"] is not None else None
    result["open_dt"] = row["open_dt"].isoformat() if row["open_dt"] else None
    result["close_dt"] = row["close_dt"].isoformat() if row["close_dt"] else None
    result["notice_type"] = notice_type
    result["bid_status"] = bid_status
    result["notice_status_label"] = notice_status_label(notice_type, row["stage"], bid_status)
    result["work_type_label"] = work_type_label(notice_type, row["biz_type"])

    summary_row = conn.execute(
        select(analysis.c.summary)
        .where(analysis.c.notice_id == notice_id, analysis.c.step == "A2_structure", analysis.c.status == "done")
        .order_by(analysis.c.ver.desc())
        .limit(1)
    ).first()
    result["ai_summary"] = summary_row.summary if summary_row else None

    result["strategy"] = None
    result["liked"] = False
    if customer_id is not None:
        strategy_row = conn.execute(
            select(notice_strategy.c.status, notice_strategy.c.strategy_md)
            .where(notice_strategy.c.customer_id == customer_id, notice_strategy.c.notice_id == notice_id)
        ).first()
        if strategy_row is not None and strategy_row.status == "done":
            result["strategy"] = {"status": strategy_row.status, "strategy_md": strategy_row.strategy_md}
        result["liked"] = get_like_state(conn, customer_id, notice_id)

    return result


def _ensure_notice_analyzed(notice_id: int) -> None:
    """A1(첨부 추출)·A2(구조화)가 아직 안 됐으면 최선을 다해 실행한다 — 이미 진행/완료됐거나
    (AnalysisInProgressError/StructuringInProgressError) 이 파일럿이 지원 안 하는 사이트거나
    (UnsupportedSourceError) API 키가 없는 등 어떤 이유로든 실패해도 조용히 넘어간다(전략
    생성 자체는 지금 있는 정보만으로 계속 진행)."""
    try:
        with engine.begin() as conn:
            run_extraction_pilot(conn, notice_id)
    except (AnalysisInProgressError, UnsupportedSourceError):
        pass
    except Exception:  # noqa: BLE001 — 추출 실패해도 전략 생성은 계속 진행
        pass

    # try/except를 with 블록 안에 둬야 한다(2026-09-08) — 밖에 두면 run_structuring이
    # 실패를 conn에 기록한 뒤 다시 던진 예외가 이 with engine.begin() 블록을 통째로
    # 롤백시켜 방금 기록한 "failed" 상태까지 같이 사라진다(pending_analysis.py와 같은 버그).
    with engine.begin() as conn:
        try:
            # 상시 Haiku(가장 저렴) — pending_analysis.py의 자동 A2와 같은 모델 선택 원칙.
            run_structuring_for_notice(conn, notice_id, model="claude-haiku-4-5-20251001")
        except Exception:  # noqa: BLE001 — A1 실패·이미 완료 등 어떤 이유든 계속 진행
            pass


def _build_prompt(notice_info: dict, profile_md: str | None) -> str:
    notice_json = json.dumps(
        {k: v for k, v in notice_info.items() if k != "ai_summary"}, ensure_ascii=False, indent=2
    )
    parts = [f"[공고 정보]\n{notice_json}"]
    if notice_info.get("ai_summary"):
        parts.append(f"[공고 요구사항 요약(AI 추출)]\n{json.dumps(notice_info['ai_summary'], ensure_ascii=False, indent=2)}")
    parts.append(f"[이 회사 프로필]\n{profile_md if profile_md else '(아직 프로필 요약이 없음)'}")
    return "\n\n".join(parts)


def get_or_generate_strategy(customer_id: int, notice_id: int, *, model: str = DEFAULT_MODEL) -> dict:
    """멱등 get-or-create. 반환 status: "done"(strategy_md 포함) · "pending"(다른 요청이
    생성 중 — 잠시 후 다시 호출) · 예외(LLMNotConfiguredError·NoticeNotFoundError 등)."""
    if model not in PRICING_PER_MTOK:
        raise ValueError(f"허용되지 않은 모델: {model} (허용: {', '.join(PRICING_PER_MTOK)})")

    with engine.begin() as conn:
        claimed = conn.execute(
            pg_insert(notice_strategy)
            .values(customer_id=customer_id, notice_id=notice_id, status="pending")
            .on_conflict_do_nothing(index_elements=["customer_id", "notice_id"])
            .returning(notice_strategy.c.id)
        ).first()

    if claimed is None:
        with engine.connect() as conn:
            existing = conn.execute(
                select(notice_strategy.c.id, notice_strategy.c.status, notice_strategy.c.strategy_md, notice_strategy.c.model, notice_strategy.c.cost_usd)
                .where(notice_strategy.c.customer_id == customer_id, notice_strategy.c.notice_id == notice_id)
            ).mappings().one()
        if existing["status"] == "done":
            return {"status": "done", "strategy_md": existing["strategy_md"], "model": existing["model"], "cost_usd": float(existing["cost_usd"])}
        if existing["status"] == "pending":
            return {"status": "pending"}
        # failed — 재시도 허용(원자적으로 실패→대기 전환에 성공한 요청만 이어서 생성)
        with engine.begin() as conn:
            retried = conn.execute(
                update(notice_strategy)
                .where(notice_strategy.c.id == existing["id"], notice_strategy.c.status == "failed")
                .values(status="pending", error_message=None)
                .returning(notice_strategy.c.id)
            ).first()
        if retried is None:
            return {"status": "pending"}

    def _mark_failed(message: str) -> None:
        with engine.begin() as conn:
            conn.execute(
                update(notice_strategy)
                .where(notice_strategy.c.customer_id == customer_id, notice_strategy.c.notice_id == notice_id)
                .values(status="failed", error_message=message[:500], updated_at=datetime.now(timezone.utc))
            )

    if not settings.anthropic_api_key:
        _mark_failed("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        raise LLMNotConfiguredError("ANTHROPIC_API_KEY가 설정되지 않았습니다 — infra/.env에 추가한 뒤 재기동하세요.")

    _ensure_notice_analyzed(notice_id)

    with engine.connect() as conn:
        notice_info = get_public_notice_summary(conn, notice_id)
        profile_md = conn.execute(select(customer.c.profile_summary_md).where(customer.c.id == customer_id)).scalar_one_or_none()

    if notice_info is None:
        _mark_failed("공고를 찾을 수 없습니다.")
        raise NoticeNotFoundError(f"공고를 찾을 수 없습니다: {notice_id}")

    payload = {
        "model": model,
        "max_tokens": 3000,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": _build_prompt(notice_info, profile_md)}],
    }
    try:
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
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        text_block = next((b for b in body.get("content", []) if b.get("type") == "text"), None)
        if text_block is None:
            raise RuntimeError("모델이 텍스트로 응답하지 않았습니다.")
        strategy_md = text_block["text"]
        cost = (input_tokens / 1_000_000) * PRICING_PER_MTOK[model]["input"] + (
            output_tokens / 1_000_000
        ) * PRICING_PER_MTOK[model]["output"]
    except Exception as exc:
        _mark_failed(str(exc))
        raise

    with engine.begin() as conn:
        conn.execute(
            update(notice_strategy)
            .where(notice_strategy.c.customer_id == customer_id, notice_strategy.c.notice_id == notice_id)
            .values(
                status="done", strategy_md=strategy_md, model=model,
                input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=round(cost, 4),
                updated_at=datetime.now(timezone.utc),
            )
        )

    return {"status": "done", "strategy_md": strategy_md, "model": model, "cost_usd": round(cost, 4)}
