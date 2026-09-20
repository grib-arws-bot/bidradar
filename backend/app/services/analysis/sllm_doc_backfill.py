"""사내 sLLM(C, classify-doc) 과거 데이터 백필(2026-09-20, 의사결정_로그 179/182번).

176번에서 C를 A1 추출 파이프라인에 연결했지만, 그건 **이후 새로 추출되는 문서**에만
적용된다. 이미 추출 완료된 기존 analysis_doc(27,000여 건)에는 소급 적용되지 않는다.
이 모듈은 이미 저장된 텍스트만 다시 classify_doc에 태워 공통문서면 재분류한다 — 실제
재추출(다운로드·파싱)은 하지 않는다.

**182번 재설계 — CLI 1회성 명령에서 스케줄러 상시 배치로 전환**: 처음엔(179번) 관리자가
`python -m app.cli`로 수동 실행하는 1회성 스크립트였다. 그런데 27,000여 건을 문서당
2~8초짜리 sLLM 호출로 처리하면 하루 이상 걸리는데, 그 스크립트가 관리자의 SSH 세션에
매달려 있어 PC를 끄면 끊겼다 — "자동화는 특정 세션·브라우저에 의존하면 안 되고 서버가
끝까지 책임져야 한다"는 기존 원칙(sllm_topic_match.py의 B와 동일)을 이것도 어기고
있었다. `embeddings.py`/`sllm_topic_match.py`와 완전히 같은 "미완료 항목 배치" 패턴으로
바꿔 `run_pending_backlog`(스케줄러, 10분 주기)가 서버에서 알아서 처리하게 한다 — 관리자
PC나 SSH 세션과 완전히 무관해졌다.

analysis_pilot.py의 라이브 분류(_reclassify_as_boilerplate_if_sllm_agrees)와 판정 기준을
반드시 맞춘다(미리보기 길이 1,000자 등) — 같은 문서가 라이브냐 백필이냐에 따라 다르게
판정되면 안 된다.
"""

from __future__ import annotations

import logging

import requests
from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from app.db import engine
from app.models import analysis_doc
from app.services.sllm_client import SllmError, SllmNotConfiguredError, classify_doc

logger = logging.getLogger("bidradar.sllm_doc_backfill")

DEFAULT_BATCH_LIMIT = 200  # embeddings.py/sllm_topic_match.py와 동일한 상한 원칙
_SLLM_CLASSIFY_PREVIEW_CHARS = 1000  # analysis_pilot.py의 라이브 분류와 동일 — 기준 통일


def _pending_doc_ids(conn: Connection, analysis_id: int | None, batch_limit: int) -> list[int]:
    """sLLM으로 아직 확인 안 한(sllm_checked_at IS NULL) 추출 성공 문서 id 목록.

    analysis_id는 sllm_topic_match.py의 source_id 필터와 같은 목적(테스트가 임시 데이터
    하나로 범위를 좁혀 공유 dev DB의 실제 데이터를 안 건드리게)의 선택적 필터."""
    stmt = (
        select(analysis_doc.c.id)
        .where(
            analysis_doc.c.sllm_checked_at.is_(None),
            analysis_doc.c.extract_ok.is_(True),
            analysis_doc.c.text.is_not(None),
        )
        .order_by(analysis_doc.c.id)
        .limit(batch_limit)
    )
    if analysis_id is not None:
        stmt = stmt.where(analysis_doc.c.analysis_id == analysis_id)
    return conn.execute(stmt).scalars().all()


def _check_one_doc(doc_id: int) -> bool:
    """문서 1건을 sLLM으로 재검사한다. 공통문서로 판정되면 True를 반환하고
    analysis_pilot.py의 라이브 분류와 동일하게 extract_ok=False·text=None으로 갱신한다.

    개별 문서 처리 실패(SllmError, 예: malformed_output)는 여기서 삼킨다 — 온도 0으로
    돌려도 같은 텍스트는 같은 이유로 계속 실패하는 경향이 있어(sllm_verification.py
    참고), sllm_checked_at은 그대로 찍어 다음 회차에 똑같은 실패를 반복하지 않는다
    (판정 불능으로 원래 상태 유지, 재분류는 안 됨). sLLM 서버 자체가 미설정이거나
    연결이 끊긴 경우(SllmNotConfiguredError·연결 오류)는 이 문서만의 문제가 아니라
    나머지도 다 실패할 상황이므로 여기서 삼키지 않고 그대로 올려 호출부가 배치
    전체를 중단하게 한다."""
    with engine.begin() as conn:
        row = conn.execute(select(analysis_doc.c.text).where(analysis_doc.c.id == doc_id)).first()
        if row is None:
            return False
        preview = row.text[:_SLLM_CLASSIFY_PREVIEW_CHARS]

        try:
            result = classify_doc(preview, trace_id=f"backfill_doc_{doc_id}")
        except SllmError as exc:
            logger.warning("sLLM 호출 실패로 건너뜀(analysis_doc id=%s): %s", doc_id, exc)
            conn.execute(analysis_doc.update().where(analysis_doc.c.id == doc_id).values(sllm_checked_at=func.now()))
            return False

        output = result.get("output", {})
        is_boilerplate = bool(output.get("is_boilerplate"))
        update_values = {"sllm_checked_at": func.now()}
        if is_boilerplate:
            reason = output.get("reason", "")
            error_msg = f"공통 문서로 판단되어 제외(sLLM 백필: {reason})" if reason else "공통 문서로 판단되어 제외(sLLM 백필)"
            update_values.update(extract_ok=False, text=None, error=error_msg)
        conn.execute(analysis_doc.update().where(analysis_doc.c.id == doc_id).values(**update_values))
        return is_boilerplate


def run_pending_sllm_doc_backfill(analysis_id: int | None = None, *, batch_limit: int = DEFAULT_BATCH_LIMIT) -> dict:
    """대기 중인 문서를 배치로 처리한다. sLLM이 미설정이거나 연결이 끊기면(타임아웃·
    connection refused 등) 그 시점에서 배치를 중단한다(checked_at을 안 찍은 문서는 다음
    회차에 재시도) — 서버가 죽은 상태로 나머지를 계속 두드리며 시간을 낭비하지 않는다.
    analysis_id는 테스트가 임시 데이터로 범위를 좁힐 때만 쓰는 선택적 필터."""
    with engine.connect() as conn:
        candidates = _pending_doc_ids(conn, analysis_id, batch_limit)

    if not candidates:
        return {"candidates": 0, "checked": 0, "reclassified": 0}

    checked = 0
    reclassified = 0
    for doc_id in candidates:
        try:
            if _check_one_doc(doc_id):
                reclassified += 1
            checked += 1
        except (SllmNotConfiguredError, requests.exceptions.RequestException) as exc:
            logger.info("sLLM 문서 백필 중단(%s) — 나머지는 다음 회차에 재시도", exc)
            break
    return {"candidates": len(candidates), "checked": checked, "reclassified": reclassified}
