"""첨부문서 자동 추출(A1)·AI 자동분석(A2)을 공고 목록 수집(app/collector/runner.py)에서
분리한 후속 패스(2026-09-05).

전에는 run_source()가 신규 공고를 발견할 때마다 그 자리에서 동기로 A1(첨부파일 다운로드)을
실행했다 — 첫 백필처럼 신규 건이 수백 개 몰리면 그 다운로드들이 전부 run_source() 호출부가
감싼 하나의 트랜잭션 안에 들어가 오래 열려있게 되고, 그 트랜잭션이 잡은 락이 다른 작업
(스키마 마이그레이션 등)까지 막는 사고가 실제로 발생했다(2026-09-05).

이 모듈은 "아직 처리 안 된 공고"를 찾아 **공고 하나마다 별도의 짧은 트랜잭션**으로 처리한다.
목록 수집(빠름, 자주 실행 가능)과 첨부 처리(느릴 수 있음)를 완전히 분리해 실행 시점도
독립적으로 가져갈 수 있게 한다 — 예: 목록만 자주 수집하고, 첨부 처리는 별도 주기로.

source.auto_extract/auto_analyze가 "관리자가 미리 정해둔 설정"이라 CLAUDE.md S8 원칙 3
("자동 실행 금지")과 충돌하지 않는다는 판단은 그대로 유지(2026-09-05 사용자 확정, 의사결정
로그 54·55번).
"""

from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.engine import Connection

from app.db import engine
from app.models import analysis, notice, source
from app.services.analysis.structure import run_structuring_for_notice
from app.services.analysis_pilot import AnalysisInProgressError, UnsupportedSourceError, run_extraction_pilot
from app.services.analysis_worker import submit as submit_background

# 한 번 호출에 처리할 최대 건수 — 무제한으로 돌면 이것도 오래 걸릴 수 있으므로 상한을 둔다.
# 남은 게 있으면 여러 번 다시 호출하면 된다(각 호출은 여전히 공고 단위 짧은 트랜잭션이라 안전).
DEFAULT_BATCH_LIMIT = 200


def _pending_extraction_notice_ids(conn: Connection, source_id: int | None, limit: int) -> list[int]:
    """auto_extract가 켜진 소스 중 아직 analysis 레코드가 하나도 없는 공고(=한 번도 A1을
    시도한 적 없는 공고)를 찾는다. 이미 실패 이력이 있는 건은 자동으로 재시도하지 않는다
    (무한 재시도 방지 — 실패 원인을 사람이 보고 판단해야 함)."""
    stmt = (
        select(notice.c.id)
        .select_from(notice)
        .join(source, source.c.id == notice.c.source_id)
        .where(source.c.auto_extract.is_(True), ~notice.c.id.in_(select(analysis.c.notice_id)))
        .order_by(notice.c.id)
        .limit(limit)
    )
    if source_id is not None:
        stmt = stmt.where(notice.c.source_id == source_id)
    return conn.execute(stmt).scalars().all()


def _pending_analyze_notice_ids(conn: Connection, source_id: int | None, limit: int) -> list[int]:
    """auto_analyze가 켜진 소스 중 A1까지는 성공했지만 아직 A2(구조화)는 안 된 공고를 찾는다.
    최신 버전(ver)만 본다 — 이전 버전이 실패했어도 최신 시도가 A1_extract/done이면 대상."""
    latest_ver_sq = (
        select(analysis.c.notice_id, analysis.c.id.label("analysis_id"))
        .distinct(analysis.c.notice_id)
        .order_by(analysis.c.notice_id, analysis.c.ver.desc())
        .subquery()
    )
    stmt = (
        select(notice.c.id)
        .select_from(notice)
        .join(source, source.c.id == notice.c.source_id)
        .join(latest_ver_sq, latest_ver_sq.c.notice_id == notice.c.id)
        .join(analysis, analysis.c.id == latest_ver_sq.c.analysis_id)
        .where(
            source.c.auto_analyze.is_(True),
            analysis.c.step == "A1_extract",
            analysis.c.status == "done",
        )
        .order_by(notice.c.id)
        .limit(limit)
    )
    if source_id is not None:
        stmt = stmt.where(notice.c.source_id == source_id)
    return conn.execute(stmt).scalars().all()


def count_pending(conn: Connection, *, limit: int = 5000) -> dict:
    """전체 현황(overview) 카드용 — 대기 중인 A1·A2 건수만 센다(실제 실행은 안 함).
    limit은 카운트가 무한정 커지지 않게 하는 상한일 뿐, 실행 배치 크기와는 무관하다."""
    return {
        "extraction": len(_pending_extraction_notice_ids(conn, None, limit)),
        "analyze": len(_pending_analyze_notice_ids(conn, None, limit)),
    }


def _process_one_new_notice(notice_id: int, *, auto_analyze: bool, prefetched_raw_item: dict | None) -> None:
    """신규 공고 1건의 A1(+auto_analyze가 켜져 있으면 이어서 A2)을 처리한다. 백그라운드
    워커 스레드(app/services/analysis_worker.py)에서 실행되어 이 함수를 부른 스케줄 잡을
    막지 않는다(2026-09-15) — 나라장터 440건이 몰려 2시간 걸린 회차가 같은 분 이후 예정된
    다른 소스의 수집까지 전부 건너뛰게 만든 사고(run_due_sources가 max_instances=1인 단일
    잡이라 이 소스 하나에 발이 묶이면 나머지 소스도 그 시각을 못 탐) 이후 사용자 지시로 도입."""
    try:
        with engine.begin() as conn:
            run_extraction_pilot(conn, notice_id, prefetched_raw_item=prefetched_raw_item)
    except (AnalysisInProgressError, UnsupportedSourceError):
        return
    except Exception:  # noqa: BLE001 — 공고 하나의 실패가 워커 스레드를 죽이면 안 됨
        return
    if not auto_analyze:
        return
    with engine.begin() as conn:
        try:
            run_structuring_for_notice(conn, notice_id, model="claude-haiku-4-5-20251001")
        except Exception:  # noqa: BLE001 — 실패는 run_structuring이 이미 "failed"로 기록함
            pass


def process_new_notices(
    source_id: int,
    notice_ids: list[int],
    *,
    raw_items_by_notice_id: dict[int, dict] | None = None,
    background: bool = False,
) -> dict:
    """방금 수집한 공고(notice_ids)만 콕 집어 A1·A2를 실행한다(2026-09-07 사용자 지시).

    run_pending_analysis()의 백로그 큐(오래된 것부터, batch_limit 상한)에 신규 공고가 밀려서
    한참 뒤로 처리되는 문제가 실측 확인됐다(나라장터 한 소스에 미처리 2천여 건이 쌓여있어
    방금 수집한 12건이 이번 실행에서 아예 도달하지 못함) — 이 함수는 그 큐를 아예 보지 않고
    notice_ids만 대상으로 하므로 잔고 규모와 무관하게 항상 즉시 처리된다. 오래된 잔고 자체를
    비우려면 여전히 관리자가 수동으로 process-pending(run_pending_analysis)을 돌려야 한다.

    raw_items_by_notice_id(2026-09-08) — g2b 계열 수집 시 이미 받아둔 원본 API 항목을
    run_extraction_pilot에 그대로 넘긴다. 안 넘기면(예: 백로그 재처리) run_extraction_pilot이
    나라장터 목록 API를 공고 하나마다 다시 실시간 호출하는데, 실측 발견 — 사전규격 223건을
    수집한 직후 이 함수가 223번 재호출하고 있었고, apis.data.go.kr이 불안정한 날엔 그중 다수가
    조용히 실패해 "첨부 없음"으로 잘못 기록됐다. 방금 수집한 것과 같은 트랜잭션에서 이미
    받은 데이터를 재사용하면 이 재호출 자체가 없어진다.

    background(2026-09-15, 기본 False) — True면 공고 하나하나를 analysis_worker(동시 2개
    제한 스레드풀)에 제출만 하고 완료를 기다리지 않는다. run_source_and_process_pending()이
    이 값을 True로 넘겨 실제 자동 수집 경로에서 쓴다 — 그래야 나라장터처럼 신규 건이 몰려도
    수집을 부른 스케줄 잡이 첨부분석 시간만큼 묶이지 않는다. 이 경우 반환값의 auto_extracted는
    "제출된 건수"일 뿐 "완료된 건수"가 아니다(실제 완료 여부는 공고 상세 화면에서 확인). A2는
    A1이 아직 안 끝난 시점이라 여기서 후보를 셀 수 없으므로, auto_analyze가 켜진 소스라도
    A2는 10분마다 도는 run_pending_backlog(A1이 done으로 바뀐 뒤 그 잔고 스캔에서 자연히
    잡힘)에 맡긴다 — 지연은 최대 10분, 대신 스케줄이 절대 안 막힌다는 게 이번 개선의 핵심.
    background=False(기본값, 테스트·CLI 등 동기 호출부)는 기존과 동일하게 완료까지 기다린다.

    첨부분석·AI분석 여부는 각 소스 설정(auto_extract/auto_analyze)을 그대로 따른다."""
    if not notice_ids:
        return {"extraction_candidates": 0, "auto_extracted": 0, "analyze_candidates": 0, "auto_analyzed": 0}
    raw_items_by_notice_id = raw_items_by_notice_id or {}

    with engine.connect() as conn:
        src = conn.execute(
            select(source.c.auto_extract, source.c.auto_analyze).where(source.c.id == source_id)
        ).mappings().first()
    if src is None:
        return {"extraction_candidates": 0, "auto_extracted": 0, "analyze_candidates": 0, "auto_analyzed": 0}

    extraction_candidates = notice_ids if src["auto_extract"] else []

    if background:
        for notice_id in extraction_candidates:
            submit_background(
                _process_one_new_notice,
                notice_id,
                auto_analyze=src["auto_analyze"],
                prefetched_raw_item=raw_items_by_notice_id.get(notice_id),
            )
        return {
            "extraction_candidates": len(extraction_candidates),
            "auto_extracted": len(extraction_candidates),  # 제출 완료 건수 — 실제 완료는 아님(백그라운드 진행 중)
            "analyze_candidates": len(extraction_candidates) if src["auto_analyze"] else 0,
            "auto_analyzed": 0,  # A1이 끝나야 알 수 있어 여기선 항상 0 — 실제 결과는 run_pending_backlog가 이어받음
        }

    auto_extracted = 0
    for notice_id in extraction_candidates:
        try:
            with engine.begin() as conn:
                run_extraction_pilot(conn, notice_id, prefetched_raw_item=raw_items_by_notice_id.get(notice_id))
            auto_extracted += 1
        except (AnalysisInProgressError, UnsupportedSourceError):
            pass
        except Exception:  # noqa: BLE001 — 공고 하나의 실패가 나머지를 막으면 안 됨
            pass

    auto_analyzed = 0
    analyze_candidates: list[int] = []
    if src["auto_analyze"]:
        with engine.connect() as conn:
            analyze_candidates = conn.execute(
                select(analysis.c.notice_id).where(
                    analysis.c.notice_id.in_(notice_ids), analysis.c.step == "A1_extract", analysis.c.status == "done",
                )
            ).scalars().all()

    for notice_id in analyze_candidates:
        # try/except를 반드시 이 with 블록 **안에**(같은 트랜잭션) 둬야 한다(2026-09-08 실측
        # 버그) — 밖에 두면 run_structuring이 실패를 conn에 기록한 뒤 다시 던진 예외가 이
        # with engine.begin() 블록을 통째로 롤백시켜, 방금 기록한 "failed" 상태까지 같이
        # 사라진다. 그러면 "시도했다가 실패"와 "아예 시도 안 함"이 DB에서 구분이 안 돼
        # CLAUDE.md S8 "조용한 실패 금지"를 어기게 된다(IRIS 접수예정 자동수집 중 공고 1건이
        # 실제로 이렇게 흔적 없이 스킵됨).
        with engine.begin() as conn:
            try:
                run_structuring_for_notice(conn, notice_id, model="claude-haiku-4-5-20251001")
                auto_analyzed += 1
            except Exception:  # noqa: BLE001 — 공고 하나의 실패가 나머지를 막으면 안 됨
                pass

    return {
        "extraction_candidates": len(extraction_candidates),
        "auto_extracted": auto_extracted,
        "analyze_candidates": len(analyze_candidates),
        "auto_analyzed": auto_analyzed,
    }


def run_pending_analysis(source_id: int | None = None, *, batch_limit: int = DEFAULT_BATCH_LIMIT) -> dict:
    """대기 중인 A1·A2를 공고 단위로 각각 별도 트랜잭션에서 실행한다. source_id를 주면 그
    소스만, 생략하면 auto_extract/auto_analyze가 켜진 모든 소스를 대상으로 한다."""
    auto_extracted = 0
    with engine.connect() as conn:
        extraction_candidates = _pending_extraction_notice_ids(conn, source_id, batch_limit)

    for notice_id in extraction_candidates:
        try:
            with engine.begin() as conn:
                run_extraction_pilot(conn, notice_id)
            auto_extracted += 1
        except (AnalysisInProgressError, UnsupportedSourceError):
            pass
        except Exception:  # noqa: BLE001 — 공고 하나의 실패가 나머지 배치를 막으면 안 됨
            pass

    auto_analyzed = 0
    with engine.connect() as conn:
        analyze_candidates = _pending_analyze_notice_ids(conn, source_id, batch_limit)

    for notice_id in analyze_candidates:
        # try/except를 with 블록 안에 둬야 실패 기록이 롤백 없이 커밋된다(위 process_new_
        # notices와 같은 이유, 2026-09-08).
        with engine.begin() as conn:
            try:
                # 항상 Haiku(가장 저렴한 모델)로만 — 모델 선택까지 자동화하지 않는다.
                run_structuring_for_notice(conn, notice_id, model="claude-haiku-4-5-20251001")
                auto_analyzed += 1
            except Exception:  # noqa: BLE001 — 공고 하나의 실패가 나머지 배치를 막으면 안 됨
                pass

    return {
        "extraction_candidates": len(extraction_candidates),
        "auto_extracted": auto_extracted,
        "analyze_candidates": len(analyze_candidates),
        "auto_analyzed": auto_analyzed,
    }
