"""A1(첨부추출)·A2(AI분석)를 수집 스레드와 분리해 돌리는 작은 백그라운드 워커 풀(2026-09-15).

배경: `run_source_and_process_pending()`가 수집 직후 새 공고의 A1(+A2)을 같은 함수 호출 안에서
동기로 실행했다 — 나라장터처럼 한 번에 수백 건이 몰리면(2026-09-14 실측: 440건, 약 2시간) 그
시간 동안 `run_due_sources`(매 분 정각에 도는 스케줄 잡, `max_instances=1`)가 이 소스 하나를
처리하는 데 발이 묶여, 같은 시각 이후 예정된 다른 소스의 수집이 전부 건너뛰어지는 사고로
이어졌다(사용자 지적: "나라장터가 왜 2시간이나 걸린거야"). 수집(빠름)과 첨부분석(느릴 수
있음)을 별도 스레드로 분리해 이 문제를 없앤다.

CLAUDE.md "Redis·Celery 도입 금지, 큐가 필요하면 DB 테이블" — 그래서 메시지 브로커를 새로
두지 않고 표준 라이브러리 ThreadPoolExecutor 하나만 쓴다. "제출된 작업 목록" 같은 별도 큐
테이블도 필요 없다 — pending_analysis.py의 _pending_extraction_notice_ids/
_pending_analyze_notice_ids가 이미 "아직 처리 안 된 공고"를 notice/analysis 테이블에서 직접
찾아내므로(=DB 자체가 큐), 여기서는 그 작업을 몇 개까지 "동시에" 돌릴지만 관리하면 된다.

S8 원칙 "분석 워커 동시 실행 상한 2(prod 서버 사양이 작음)"를 그대로 이 풀의 크기로 삼는다.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger("bidradar.analysis_worker")

MAX_ANALYSIS_WORKERS = 2

_executor = ThreadPoolExecutor(max_workers=MAX_ANALYSIS_WORKERS, thread_name_prefix="analysis-worker")


def submit(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
    """A1/A2 작업 하나를 워커 풀에 제출하고 즉시 반환한다(호출부를 막지 않음).

    fn 자신이 이미 자기 실패를 삼키고 DB에 기록하는 게 정상 경로다(run_extraction_pilot·
    run_structuring은 실패 시 analysis.status="failed"로 남긴다) — 그래도 fn 밖에서 터지는
    진짜 예상 못 한 예외(DB 커넥션 자체 실패 등)까지 조용히 사라지면 안 되므로(CLAUDE.md
    "조용한 실패 금지") 완료 콜백에서 한 번 더 로그를 남긴다.
    """
    future = _executor.submit(fn, *args, **kwargs)

    def _log_if_failed(f: Future) -> None:
        exc = f.exception()
        if exc is not None:
            logger.exception("백그라운드 분석 작업이 예상치 못하게 실패했습니다", exc_info=exc)

    future.add_done_callback(_log_if_failed)
    return future
