"""S8 심층 분석 파일럿(A0+A1만, 2026-09-03) — 구현스펙 07절 전체(A0~A7) 중 "실제 사이트에서
웹페이지+첨부문서를 받아 텍스트로 추출"까지만 하는 첫 단계. LLM 호출(A2 이후)은 이번 범위
밖 — ANTHROPIC_API_KEY가 아직 없기도 하고, 사용자가 "추출까지만" 하자고 확정함.

지금은 IRIS(접수예정·공모예고, 둘 다 www.iris.go.kr) 상세페이지만 지원한다 — 첨부파일
목록이 JS onclick(f_bsnsAncm_downloadAtchFile)에 박혀 있어 사이트별로 뜯어봐야 하는 구조라,
다른 소스(K-water·과기정통부 등)를 추가하려면 그 사이트용 발견 함수를 따로 만들어야 한다.

원본 파일은 저장하지 않는다(2026-09-03 결정) — notice.url이 항상 있어 필요하면 재다운로드
가능하고, 저장공간이 무한정 느는 것도 피한다. 추출된 텍스트만 analysis_doc.text에 남는다.
zip(신청서 양식 등)은 건너뛴다 — 공고 "내용" 분석이 목적이라 채우는 서식 자체는 텍스트
추출 대상이 아니다.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.models import analysis, analysis_doc, notice
from app.security.url_guard import fetch
from app.services.document_extract import extract_document

_IRIS_ATCH_RE = re.compile(
    r"f_bsnsAncm_downloadAtchFile\('([^']+)','([^']+)','([^']+)'\s*,'(\d+)'\)"
)
_IRIS_MAX_DOC_BYTES = 50 * 1024 * 1024  # 문서 다운로드는 url_guard 기본 10MB보다 상향(스펙 주석과 동일 원칙)


class AnalysisInProgressError(Exception):
    """동일 공고에 이미 진행 중인 분석이 있음 — 중복 실행 거부(S8 원칙 3)."""


class UnsupportedSourceError(Exception):
    """이 파일럿이 아직 지원하지 않는 사이트(IRIS 외)."""


def _discover_iris_attachments(html: str) -> list[tuple[str, str, str, int]]:
    """(atchDocId, atchFileId, fileName, fileSize) 목록. zip은 여기서 이미 제외한다."""
    found = []
    for atch_doc_id, atch_file_id, file_name, file_size in _IRIS_ATCH_RE.findall(html):
        if file_name.lower().endswith(".zip"):
            continue
        found.append((atch_doc_id, atch_file_id, file_name, int(file_size)))
    return found


def _iris_download_url(atch_doc_id: str, atch_file_id: str) -> str:
    # contents/section*.xml 발견 때와 동일 — contextRoot는 항상 빈 문자열(실측 확인).
    return (
        "https://www.iris.go.kr/comm/file/fileDownload.do"
        f"?atchDocId={quote(atch_doc_id)}&atchFileId={quote(atch_file_id)}"
    )


def _kind_from_filename(filename: str) -> str:
    lower = filename.lower()
    for ext in ("pdf", "hwpx", "hwp"):
        if lower.endswith(f".{ext}"):
            return ext
    return "other"


def run_extraction_pilot(conn: Connection, notice_id: int) -> dict:
    """A0(입력 준비)+A1(문서 추출)만 수행하고 analysis/analysis_doc에 남긴다.

    한 트랜잭션 안에서 동기로 전부 처리한다 — 아직 백그라운드 워커가 없어서(CLAUDE.md:
    Redis·Celery 도입 금지, 큐가 필요하면 DB 테이블) 진짜 동시 요청 경합까지 완벽히 막지는
    못하지만(같은 트랜잭션이라 "진행 중" 표시를 커밋하기 전엔 다른 요청이 못 봄), 사람이
    버튼을 눌러서 시작하는 이번 파일럿 범위에선 충분하다.
    """
    row = conn.execute(select(notice.c.url).where(notice.c.id == notice_id)).first()
    if row is None:
        raise ValueError(f"공고를 찾을 수 없음: {notice_id}")
    notice_url = row.url

    if "iris.go.kr" not in notice_url:
        raise UnsupportedSourceError("이 파일럿은 아직 IRIS 공고만 지원합니다.")

    existing = conn.execute(
        select(analysis.c.id).where(analysis.c.notice_id == notice_id, analysis.c.status.in_(("queued", "running")))
    ).first()
    if existing:
        raise AnalysisInProgressError(f"이미 진행 중인 분석이 있습니다(analysis id={existing.id}).")

    next_ver = conn.execute(
        select(analysis.c.ver).where(analysis.c.notice_id == notice_id).order_by(analysis.c.ver.desc())
    ).first()
    ver = (next_ver.ver + 1) if next_ver else 1

    analysis_id = conn.execute(
        analysis.insert().values(
            notice_id=notice_id,
            source_kind="notice",
            input_ref=notice_url,
            status="running",
            step="A1_extract",
            started_at=datetime.now(timezone.utc),
            ver=ver,
        ).returning(analysis.c.id)
    ).scalar_one()

    html = fetch(notice_url).text
    attachments = _discover_iris_attachments(html)

    docs_result = []
    any_ok = False
    for atch_doc_id, atch_file_id, file_name, _file_size in attachments:
        kind = _kind_from_filename(file_name)
        doc_row = {"name": file_name, "kind": kind, "bytes": 0, "sha256": "", "extract_method": None, "extract_ok": False, "error": None, "text": None}

        if kind == "other":
            doc_row["error"] = f"지원하지 않는 형식: {file_name}"
        else:
            try:
                download_url = _iris_download_url(atch_doc_id, atch_file_id)
                content = fetch(download_url, max_bytes=_IRIS_MAX_DOC_BYTES).content
                doc_row["bytes"] = len(content)
                doc_row["sha256"] = hashlib.sha256(content).hexdigest()
                result = extract_document(file_name, content)
                doc_row["extract_method"] = result.method
                doc_row["extract_ok"] = result.ok
                doc_row["text"] = result.text
                doc_row["error"] = result.error
                any_ok = any_ok or result.ok
            except Exception as exc:  # noqa: BLE001 — 폴백 사슬 마지막 보고 지점, 조용히 삼키지 않는다
                doc_row["error"] = str(exc)

        conn.execute(analysis_doc.insert().values(analysis_id=analysis_id, **doc_row))
        docs_result.append(doc_row)

    final_status = "done" if (not attachments or any_ok) else "failed"
    conn.execute(
        analysis.update()
        .where(analysis.c.id == analysis_id)
        .values(status=final_status, step="A1_extract", finished_at=datetime.now(timezone.utc))
    )

    return {
        "analysis_id": analysis_id,
        "status": final_status,
        "attachments_found": len(attachments),
        "docs": docs_result,
    }


def get_latest_extraction(conn: Connection, notice_id: int) -> dict | None:
    """상세 페이지가 재방문 시에도 지난 추출 결과를 보여줄 수 있도록 최신 analysis 1건 + 문서."""
    row = conn.execute(
        select(analysis.c.id, analysis.c.status, analysis.c.step, analysis.c.finished_at, analysis.c.ver)
        .where(analysis.c.notice_id == notice_id)
        .order_by(analysis.c.ver.desc())
    ).first()
    if row is None:
        return None

    docs = conn.execute(
        select(
            analysis_doc.c.name,
            analysis_doc.c.kind,
            analysis_doc.c.extract_method,
            analysis_doc.c.extract_ok,
            analysis_doc.c.error,
            analysis_doc.c.text,
        ).where(analysis_doc.c.analysis_id == row.id)
    ).mappings().all()

    return {
        "analysis_id": row.id,
        "status": row.status,
        "step": row.step,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "ver": row.ver,
        "docs": [dict(d) for d in docs],
    }
