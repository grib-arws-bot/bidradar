"""사내 sLLM(A, extract-requirements) 요구사항 추출 미리보기(2026-09-20, 의사결정_로그 178번).

A2(structure.py, Haiku)는 정확하지만 호출마다 비용이 든다. 사용자가 A2를 실제로 돌릴
가치가 있는지 미리 가늠할 수 있게, 이미 A1에서 추출된 같은 문서 텍스트를 무료 사내
sLLM으로 먼저 훑어 요구사항 후보를 보여준다. **A2를 대체하지 않는다** — 이 결과는
`analysis_requirement`(match.py/A3가 읽는 테이블)에 절대 섞이지 않고, 화면에도 "미리보기"
로만 노출된다(두 계층 LLM 설계: sLLM=미리보기, Haiku=확정, product.py 173/178번 참고).

sLLM은 청크 단위로 처리해 수 분 걸릴 수 있어 동기 호출이 아니라 job 폴링 방식이다
(sLLM팀 2026-09-20 재설계, sllm_client.start_extract_requirements/get_extract_requirements_status).
이 모듈은 시작(start)과 조회(get, 필요하면 그 자리에서 폴링해 상태를 갱신)만 제공한다 —
별도 스케줄러 잡을 두지 않고 프론트엔드가 이 화면을 보고 있는 동안의 GET 호출이 폴링을
대신한다(S8 원칙 3 "자동 실행 금지"와도 맞음 — 사용자가 미리보기 화면을 열어둔 동안만 진행됨).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from app.models import analysis, analysis_sllm_preview
from app.services.analysis.structure import _collect_source_text, _latest_analysis_id
from app.services.sllm_client import (
    SllmError,
    SllmNotConfiguredError,
    get_extract_requirements_status,
    start_extract_requirements,
)
from app.services.sllm_verification import sanitize_sllm_requirements

logger = logging.getLogger("bidradar.sllm_preview")


class SllmPreviewInProgressError(Exception):
    """같은 analysis에 대해 이미 진행 중인 sLLM 미리보기 job이 있음 — 중복 호출 방지."""


def _get_preview_row(conn: Connection, analysis_id: int):
    return conn.execute(
        select(analysis_sllm_preview).where(analysis_sllm_preview.c.analysis_id == analysis_id)
    ).mappings().first()


def _to_response(row) -> dict:
    return {
        "status": row["status"],
        "chunks_processed": row["chunks_processed"],
        "chunks_total": row["chunks_total"],
        "requirements": row["requirements"],
        "rejected_ungrounded_count": row["rejected_ungrounded_count"],
        "duplicate_count": row["duplicate_count"],
        "error": row["error"],
    }


def start_sllm_preview_for_notice(conn: Connection, notice_id: int) -> dict:
    """공고 상세 화면에서 관리자가 버튼을 눌러 실행 — 그 공고의 가장 최근 A1 추출 결과를
    대상으로 sLLM job을 시작한다."""
    analysis_id = _latest_analysis_id(conn, notice_id)
    if analysis_id is None:
        raise ValueError("먼저 첨부문서 추출(A1)을 실행해야 합니다 — 진행된 분석이 없습니다.")

    existing = _get_preview_row(conn, analysis_id)
    if existing is not None and existing["status"] in ("queued", "running"):
        raise SllmPreviewInProgressError(
            f"analysis id={analysis_id}는 이미 sLLM 미리보기가 진행 중입니다 — 완료 후 다시 시도하세요."
        )

    document_text = _collect_source_text(conn, analysis_id)
    if not document_text:
        raise ValueError("추출된 문서 텍스트가 없어 미리보기를 진행할 수 없습니다(A1이 먼저 성공해야 함).")

    job = start_extract_requirements(document_text, trace_id=f"a_preview_{analysis_id}")

    values = {
        "status": job.get("status", "queued"),
        "sllm_job_id": job["job_id"],
        "chunks_processed": None,
        "chunks_total": None,
        "requirements": None,
        "rejected_ungrounded_count": None,
        "duplicate_count": None,
        "error": None,
        "started_at": datetime.now(timezone.utc),
        "finished_at": None,
    }
    if existing is None:
        conn.execute(insert(analysis_sllm_preview).values(analysis_id=analysis_id, **values))
    else:
        conn.execute(
            analysis_sllm_preview.update()
            .where(analysis_sllm_preview.c.analysis_id == analysis_id)
            .values(**values)
        )
    return {"analysis_id": analysis_id, **_to_response(values)}


def get_sllm_preview_for_notice(conn: Connection, notice_id: int) -> dict | None:
    """미리보기 상태 조회 — status가 아직 진행 중이면 그 자리에서 sLLM에 한 번 더 물어보고
    바뀐 내용을 반영한다(화면이 열려 있는 동안 프론트엔드가 이 엔드포인트를 주기적으로
    불러 폴링을 대신함)."""
    analysis_id = _latest_analysis_id(conn, notice_id)
    if analysis_id is None:
        return None

    row = _get_preview_row(conn, analysis_id)
    if row is None:
        return None
    if row["status"] not in ("queued", "running"):
        return _to_response(row)

    try:
        polled = get_extract_requirements_status(row["sllm_job_id"])
    except (SllmNotConfiguredError, SllmError) as exc:
        # 폴링 자체가 일시적으로 실패해도 진행 중 상태를 그대로 둔다 — 다음 폴링에서 재시도.
        # 근거 없이 "실패"로 단정하지 않되, 조용히 넘기지 않도록 로그는 남긴다.
        logger.warning("sLLM 미리보기 폴링 실패(analysis_id=%s): %s", analysis_id, exc)
        return _to_response(row)

    status_value = polled.get("status", row["status"])
    update_values = {
        "status": status_value,
        "chunks_processed": polled.get("chunks_processed"),
        "chunks_total": polled.get("chunks_total"),
    }
    if status_value == "done":
        source_text = _collect_source_text(conn, analysis_id)
        raw_requirements = polled.get("output", {}).get("requirements", [])
        sanitized = sanitize_sllm_requirements(raw_requirements, source_text)
        update_values.update(
            requirements=sanitized["requirements"],
            rejected_ungrounded_count=sanitized["rejected_ungrounded_count"],
            duplicate_count=sanitized["duplicate_count"],
            finished_at=datetime.now(timezone.utc),
        )
    elif status_value == "failed":
        update_values.update(
            error=polled.get("error", "sLLM 미리보기 실패(원인 미상)"),
            finished_at=datetime.now(timezone.utc),
        )

    conn.execute(
        analysis_sllm_preview.update()
        .where(analysis_sllm_preview.c.analysis_id == analysis_id)
        .values(**update_values)
    )
    row = _get_preview_row(conn, analysis_id)
    return _to_response(row)
