"""수집 스케줄러 실행 엔진 — CLAUDE.md 기술스택 "APScheduler(백엔드와 같은 이미지, 별도
프로세스)"의 실제 구현체. `docker compose run` 시 `python -m app.scheduler`로 기동한다(별도
컨테이너 — backend API 프로세스와 공유하지 않는다. 하나가 죽어도 다른 하나에 영향 없게 하기
위함이자, uvicorn 워커 재시작마다 스케줄이 중복 등록되는 것을 피하기 위함).

관리자 페이지 "데이터 수집채널"에서 소스별로 지정하는 `source.schedule_times`(최대 3개,
"HH:MM", 2026-09-05 도입)는 그동안 값만 저장되고 실제로 그 시각에 도는 실행 엔진이 없었다
(의사결정_로그 983번 항목 — "설정 UI만 만들고 실행 엔진은 다음에"는 사용자가 명시적으로
범위에서 뺀 것이었다). 2026-09-10 사용자 지시로 이 엔진을 추가한다.

시각은 관리자가 화면에 입력한 그대로 "한국 표준시(Asia/Seoul) 벽시계 시각"으로 해석한다 —
컨테이너 자체 시간대 설정에 기대지 않고 여기서 명시적으로 변환한다(컨테이너가 기본 UTC로
뜨는 게 흔해서, 여기서 안 하면 스케줄이 9시간 밀리는 사고가 날 수 있다).

매 분 정각에 깨어나 활성 소스 중 이번 분의 "HH:MM"이 schedule_times에 들어있는 소스를
찾아 `run_source_and_process_pending()`으로 수집한다. 프로세스가 그 순간 죽어있었다면(배포
직후 등) 그 회차는 그냥 건너뛴다 — 놓친 시각을 나중에 몰아서 실행하지 않는다(단순함 우선,
어차피 다음 예정 시각에 다시 돈다).
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.collector.runner import CollectionInProgressError, run_source_and_process_pending
from app.db import engine
from app.models import source
from app.services.pending_analysis import run_pending_analysis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [scheduler] %(levelname)s %(message)s")
logger = logging.getLogger("bidradar.scheduler")

KST = ZoneInfo("Asia/Seoul")


def _due_sources(now_kst: datetime) -> list[tuple[int, str]]:
    """이 시각(now_kst)의 "HH:MM"이 schedule_times에 들어있는 활성 소스의 (id, name) 목록."""
    hhmm = now_kst.strftime("%H:%M")
    with engine.connect() as conn:
        rows = conn.execute(
            select(source.c.id, source.c.name, source.c.schedule_times).where(source.c.active.is_(True))
        ).all()
    return [(row.id, row.name) for row in rows if hhmm in (row.schedule_times or [])]


def run_due_sources(now: datetime | None = None) -> list[int]:
    """이번 분에 예정된 소스를 전부 수집하고, 실제로 실행을 시도한 source_id 목록을 반환한다
    (테스트·로그 검증용). 소스 하나가 실패해도(등급 B 최소간격 위반, 이미 진행 중 등) 나머지
    소스는 계속 처리한다 — 한 소스의 문제가 다른 소스의 예정 수집을 막으면 안 된다."""
    now_kst = (now or datetime.now(KST)).astimezone(KST)
    due = _due_sources(now_kst)
    attempted: list[int] = []
    for source_id, name in due:
        attempted.append(source_id)
        try:
            result = run_source_and_process_pending(source_id)
            logger.info("[%s] %s 예약 수집 완료: fetched=%s inserted=%s", source_id, name, result.get("fetched"), result.get("inserted"))
        except CollectionInProgressError:
            logger.info("[%s] %s 이미 다른 수집이 진행 중이라 건너뜀", source_id, name)
        except Exception:  # noqa: BLE001 — 한 소스 실패가 이번 분의 다른 소스 실행을 막으면 안 됨
            logger.exception("[%s] %s 예약 수집 실패", source_id, name)
    return attempted


def run_pending_backlog() -> dict:
    """`process_new_notices`(방금 수집한 공고 전용)가 못 잡는 잔고를 주기적으로 쓸어담는다
    (2026-09-13, 의사결정_로그 126번). 웹 페이지의 "재분석" 버튼은 첨부 재추출(A1) 뒤 AI분석
    (A2)을 브라우저에서 순차 호출하는데, 그 사이 탭을 닫는 등으로 두 번째 호출이 안 나가면
    그 공고는 auto_analyze=true인 소스라도 다시는 자동으로 안 잡혔다(process_new_notices는
    "이번에 새로 수집된 공고"만 봄) — 실사례(notice_id=5476)로 발견. 사용자 지시: "수집/분석
    자동화는 웹 페이지가 떠 있든 말든 백그라운드에서 자동으로 되어야 한다" — run_due_sources와
    별개로 몇 분마다 이 함수가 대신 훑어 마저 처리한다."""
    try:
        result = run_pending_analysis()
    except Exception:  # noqa: BLE001 — 이번 회차 실패가 다음 예정 실행(run_due_sources 등)을 막으면 안 됨
        logger.exception("잔고 처리(run_pending_analysis) 실패")
        return {"extraction_candidates": 0, "auto_extracted": 0, "analyze_candidates": 0, "auto_analyzed": 0}
    if result["auto_extracted"] or result["auto_analyzed"]:
        logger.info(
            "잔고 처리 완료: 추출대상=%s 추출성공=%s 분석대상=%s 분석성공=%s",
            result["extraction_candidates"], result["auto_extracted"],
            result["analyze_candidates"], result["auto_analyzed"],
        )
    return result


def main() -> None:
    scheduler = BlockingScheduler(timezone=KST)
    scheduler.add_job(run_due_sources, CronTrigger(second=0), id="run_due_sources", max_instances=1)
    # 10분마다 — 분 단위로 도는 run_due_sources보다 훨씬 드물게(잔고 처리는 급하지 않음, 분석
    # 워커 동시실행 상한 2인 prod 사양 고려, CLAUDE.md S8).
    scheduler.add_job(run_pending_backlog, CronTrigger(minute="*/10"), id="run_pending_backlog", max_instances=1)
    logger.info("BidRadar 수집 스케줄러 시작(Asia/Seoul 기준, 매 분 정각 확인 + 10분마다 잔고 처리)")
    scheduler.start()


if __name__ == "__main__":
    main()
