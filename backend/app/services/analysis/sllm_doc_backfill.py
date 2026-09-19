"""사내 sLLM(C, classify-doc) 과거 데이터 백필(2026-09-20, 의사결정_로그 179번).

176번에서 C를 A1 추출 파이프라인에 연결했지만, 그건 **이후 새로 추출되는 문서**에만
적용된다. 이미 추출 완료된 기존 analysis_doc(현재 16,000여 건)에는 소급 적용되지 않는다.
이 모듈은 이미 저장된 텍스트만 다시 classify_doc에 태워 공통문서면 재분류하는 1회성
백필이다 — 실제 재추출(다운로드·파싱)은 하지 않는다.

analysis_pilot.py의 라이브 분류(_reclassify_as_boilerplate_if_sllm_agrees)와 판정 기준을
반드시 맞춘다(미리보기 길이 1,000자 등) — 같은 문서가 라이브냐 백필이냐에 따라 다르게
판정되면 안 된다.

새 DB 컬럼을 추가하지 않는다 — analysis_doc.id 커서(--after-id)로 재개하는 방식(CLI 인자)을
쓴다. 이미 재분류된 행(extract_ok=False)은 다음 조회에서 자연히 제외되므로 진행 상태를
별도로 기록할 필요가 없다.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.db import engine
from app.models import analysis_doc
from app.services.sllm_client import SllmError, SllmNotConfiguredError, classify_doc

logger = logging.getLogger("bidradar.sllm_doc_backfill")

_SLLM_CLASSIFY_PREVIEW_CHARS = 1000  # analysis_pilot.py의 라이브 분류와 동일 — 기준 통일


def backfill_doc_boilerplate_classification(*, after_id: int = 0, limit: int = 200, analysis_id: int | None = None) -> dict:
    """analysis_doc.id > after_id 인 것 중 extract_ok=true고 텍스트가 있는 것을 최대 limit개
    가져와 sLLM(C)로 재검사한다. 공통문서로 판정되면 analysis_pilot.py의 라이브 분류와
    동일하게 extract_ok=False·text=None으로 갱신한다(임베딩 백필이 아직 안 끝난 문서라면
    덤으로 노이즈도 줄어든다). sLLM이 미설정이면 즉시 예외를 올린다(수동 실행이므로 조용히
    건너뛰지 않는다) — 개별 문서의 일시적 오류는 건너뛰고 계속한다.

    analysis_id는 pending_analysis.py의 source_id 필터와 같은 목적(테스트가 임시 데이터
    하나로 범위를 좁혀 공유 dev DB의 실제 데이터를 안 건드리게)의 선택적 필터."""
    stmt = (
        select(analysis_doc.c.id, analysis_doc.c.text)
        .where(
            analysis_doc.c.id > after_id,
            analysis_doc.c.extract_ok.is_(True),
            analysis_doc.c.text.is_not(None),
        )
        .order_by(analysis_doc.c.id)
        .limit(limit)
    )
    if analysis_id is not None:
        stmt = stmt.where(analysis_doc.c.analysis_id == analysis_id)
    with engine.connect() as conn:
        rows = conn.execute(stmt).all()

    if not rows:
        return {"last_id": after_id, "checked": 0, "reclassified": 0}

    checked = 0
    reclassified = 0
    last_id = after_id
    for doc_id, text in rows:
        last_id = doc_id
        preview = text[:_SLLM_CLASSIFY_PREVIEW_CHARS]
        try:
            result = classify_doc(preview, trace_id=f"backfill_doc_{doc_id}")
        except SllmNotConfiguredError:
            raise
        except SllmError as exc:
            logger.warning("sLLM 호출 실패로 건너뜀(analysis_doc id=%s): %s", doc_id, exc)
            checked += 1
            continue

        checked += 1
        output = result.get("output", {})
        if output.get("is_boilerplate"):
            reason = output.get("reason", "")
            error_msg = f"공통 문서로 판단되어 제외(sLLM 백필: {reason})" if reason else "공통 문서로 판단되어 제외(sLLM 백필)"
            with engine.begin() as conn:
                conn.execute(
                    analysis_doc.update()
                    .where(analysis_doc.c.id == doc_id)
                    .values(extract_ok=False, text=None, error=error_msg)
                )
            reclassified += 1

    return {"last_id": last_id, "checked": checked, "reclassified": reclassified}
