"""이미 A1을 시도했지만 첨부 0건으로 기록된 g2b 계열 공고를 캐시된 raw_payload로
재처리한다(2026-09-08, 발주계획/사전규격 일괄재처리).

배경: 수집 직후 첨부분석이 나라장터 목록 API를 공고 하나마다 실시간으로 재호출하던 버그
(app/services/analysis_pilot.py의 _discover_g2b_attachments, 의사결정 로그 82번)가
apis.data.go.kr 불안정 때문에 발주계획·사전규격 다수 건을 "첨부 없음"으로 잘못 기록했다.
그 버그는 "방금 수집한 건"에 대해서는 이미 고쳤지만(수집 시점에 받은 데이터를 그대로
넘겨받아 재호출 자체를 안 함), 그 수정 이전에 이미 "시도 완료(0건)"로 남은 과거 건들은
run_pending_analysis()의 백로그 큐가 건드리지 않는다(analysis 레코드가 이미 있으면 대상에서
빠짐) — 이 모듈은 그 빈틈을 메우는 일회성 백필이다.

라이브 재조회로 폴백하지 않는다 — 캐시(raw_payload)에 없는 건은 "다시 시도해서 또 조용히
0건"이 되는 대신 건너뛴 건수로만 보고한다(CLAUDE.md S8 "조용한 빈 결과 금지").
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.db import engine
from app.models import analysis, analysis_doc, notice, raw_payload, source_config
from app.services.analysis_pilot import AnalysisInProgressError, UnsupportedSourceError, run_extraction_pilot
from app.services.g2b_attachments import _G2B_FAMILIES


def _empty_attachment_notice_ids(conn: Connection, source_id: int) -> list[int]:
    """A1을 이미 시도했지만(analysis.step='A1_extract' 레코드 존재) 성공한 첨부문서
    (analysis_doc.extract_ok=true)가 하나도 없는 공고."""
    ok_analysis_ids = select(analysis_doc.c.analysis_id).where(analysis_doc.c.extract_ok.is_(True))
    stmt = (
        select(notice.c.id)
        .where(
            notice.c.source_id == source_id,
            notice.c.id.in_(select(analysis.c.notice_id).where(analysis.c.step == "A1_extract")),
            ~notice.c.id.in_(select(analysis.c.notice_id).where(analysis.c.id.in_(ok_analysis_ids))),
        )
        .order_by(notice.c.id)
    )
    return conn.execute(stmt).scalars().all()


def _match_field_for_source(conn: Connection, source_id: int) -> str | None:
    cfg = conn.execute(
        select(source_config.c.config)
        .where(source_config.c.source_id == source_id)
        .order_by(source_config.c.ver.desc())
        .limit(1)
    ).scalar_one_or_none()
    endpoint = (cfg or {}).get("endpoint", "")
    for marker, match_field, _handler in _G2B_FAMILIES:
        if marker in endpoint:
            return match_field
    return None


def _build_raw_item_index(conn: Connection, source_id: int, match_field: str) -> dict[str, dict]:
    """이 소스가 과거에 수집할 때마다 남긴 raw_payload(원본 API 응답 스냅샷)를 전부 모아
    match_field 값으로 색인한다. 같은 공고가 여러 회차에 걸쳐 나타날 수 있어(정기 재수집),
    fetched_at 오름차순으로 처리해 최신 스냅샷이 이전 것을 덮어쓰게 한다."""
    index: dict[str, dict] = {}
    rows = conn.execute(
        select(raw_payload.c.body).where(raw_payload.c.source_id == source_id).order_by(raw_payload.c.fetched_at.asc())
    )
    for (body,) in rows:
        for item in body.get("items", []):
            key = item.get(match_field)
            if key:
                index[key] = item
    return index


def reprocess_empty_extractions(source_id: int) -> dict:
    """source_id의 "A1 시도 완료·첨부 0건" 공고를 캐시된 raw_payload만으로 재시도한다.
    apis.data.go.kr을 전혀 호출하지 않는다."""
    with engine.connect() as conn:
        candidate_ids = _empty_attachment_notice_ids(conn, source_id)
        match_field = _match_field_for_source(conn, source_id)
        if match_field is None or not candidate_ids:
            return {
                "candidates": len(candidate_ids),
                "no_cache_match": len(candidate_ids) if match_field is None else 0,
                "reprocessed": 0,
                "found_docs": 0,
            }
        item_index = _build_raw_item_index(conn, source_id, match_field)
        rows = conn.execute(
            select(notice.c.id, notice.c.notice_no, notice.c.extra).where(notice.c.id.in_(candidate_ids))
        ).all()

    reprocessed = 0
    found_docs = 0
    no_cache_match = 0
    for notice_id, notice_no, extra in rows:
        match_value = notice_no if match_field != "orderPlanUntyNo" else (extra or {}).get("orderPlanUntyNo")
        item = item_index.get(match_value) if match_value else None
        if item is None:
            no_cache_match += 1
            continue
        try:
            with engine.begin() as conn:
                outcome = run_extraction_pilot(conn, notice_id, prefetched_raw_item=item)
            reprocessed += 1
            if any(d.get("extract_ok") for d in outcome.get("docs", [])):
                found_docs += 1
        except (AnalysisInProgressError, UnsupportedSourceError):
            pass
        except Exception:  # noqa: BLE001 — 공고 하나의 실패가 나머지를 막으면 안 됨
            pass

    return {
        "candidates": len(candidate_ids),
        "no_cache_match": no_cache_match,
        "reprocessed": reprocessed,
        "found_docs": found_docs,
    }
