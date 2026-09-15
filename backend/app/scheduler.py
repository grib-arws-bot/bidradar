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
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.collector.runner import CollectionInProgressError, run_source_and_process_pending
from app.db import engine
from app.logging_config import configure_logging
from app.models import customer, source
from app.services.interest_report import generate_report, send_report_email
from app.services.mailer import SmtpNotConfiguredError
from app.services.pending_analysis import run_pending_analysis

# 고객 보고서 메일을 같은 분에 한꺼번에 여러 명에게 쏘지 않고 이만큼 띄운다(2026-09-14) —
# 하이웍스 이용약관 제29조2항이 "자동화 스크립트를 통한 메일 대량발송"을 금지한다고 명시돼
# 있어(의사결정_로그 9번), 자동발송을 도입하며 그때 정한 완화 조치("발송 간격 두기")를
# 실제로 반영한다. 고객 수가 많지 않아(내부 도구) 초 단위로도 충분하다.
EMAIL_SEND_SPACING_SECONDS = 5

# 2026-09-14 — 콘솔뿐 아니라 영속 파일(/app/logs/bidradar.log)에도 남긴다(app/logging_config.py) —
# 컨테이너가 재생성되면(다른 컨테이너 문제로 인한 연쇄 recreate 등) 표준출력 로그가 사라져
# 이 스케줄러의 OpenAPI 호출 이력을 못 찾은 사고(2026-09-13 쿼터 초과 조사) 재발 방지.
configure_logging("scheduler")
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


def _due_customers(now_kst: datetime) -> list[tuple[int, str]]:
    """이 시각(now_kst)의 요일(ISO, 1=월~7=일)이 report_auto_send_days에 있고 "HH:MM"이
    report_auto_send_times(2026-09-15부터 복수 지정 가능, source.schedule_times와 동일하게
    최대 3개) 중 하나와 일치하는 활성 고객의 (id, name) 목록. 둘 다 설정돼 있어야 대상이다."""
    hhmm = now_kst.strftime("%H:%M")
    weekday = now_kst.isoweekday()
    with engine.connect() as conn:
        rows = conn.execute(
            select(customer.c.id, customer.c.name, customer.c.report_auto_send_days, customer.c.report_auto_send_times)
            .where(customer.c.active.is_(True))
        ).all()
    return [
        (row.id, row.name)
        for row in rows
        if hhmm in (row.report_auto_send_times or []) and weekday in (row.report_auto_send_days or [])
    ]


def run_due_customer_emails(now: datetime | None = None) -> list[int]:
    """이번 분에 예정된 고객에게 보고서를 생성해 자동으로 메일을 보낸다(2026-09-14 사용자
    지시). 관리자가 고객 상세 화면에서 명시적으로 요일·시간을 설정해야만 대상이 되므로
    CLAUDE.md 원칙 3("자동 실행 금지")과 충돌하지 않는다 — run_due_sources의 auto_extract/
    auto_analyze와 같은 논리. 신규 관심 공고가 0건이면(보낼 내용이 없으면) 발송을 건너뛴다.

    발송 간격을 둔다(EMAIL_SEND_SPACING_SECONDS) — 의사결정_로그 9번의 완화 조치 반영."""
    now_kst = (now or datetime.now(KST)).astimezone(KST)
    due = _due_customers(now_kst)
    sent: list[int] = []
    for i, (customer_id, name) in enumerate(due):
        if i > 0:
            time.sleep(EMAIL_SEND_SPACING_SECONDS)
        try:
            report = generate_report(customer_id)
            if report is None:
                logger.info("[%s] %s 예약 발송 건너뜀: 관심주제 미설정", customer_id, name)
                continue
            if report["summary"].get("total", 0) == 0:
                logger.info("[%s] %s 예약 발송 건너뜀: 신규 관심 공고 0건", customer_id, name)
                continue
            with engine.begin() as conn:
                send_report_email(conn, customer_id, report["id"])
            sent.append(customer_id)
            logger.info("[%s] %s 예약 발송 완료: %s건", customer_id, name, report["summary"].get("total"))
        except SmtpNotConfiguredError:
            logger.warning("[%s] %s 예약 발송 실패: SMTP 미설정", customer_id, name)
        except Exception:  # noqa: BLE001 — 한 고객 실패가 다른 고객 발송을 막으면 안 됨
            logger.exception("[%s] %s 예약 발송 실패", customer_id, name)
    return sent


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
    # 2026-09-14 — 고객 보고서 메일 자동발송(요일·시간, 고객 상세 화면 설정). run_due_sources와
    # 같은 매 분 정각 체크지만 별도 job으로 둔다 — 이 job이 오래 걸려도(발송 간격 때문에)
    # run_due_sources 다음 실행을 막지 않도록(BlockingScheduler 기본 스레드풀 executor라 서로
    # 다른 job은 별도 스레드에서 돈다).
    scheduler.add_job(run_due_customer_emails, CronTrigger(second=0), id="run_due_customer_emails", max_instances=1)
    logger.info("BidRadar 수집 스케줄러 시작(Asia/Seoul 기준, 매 분 정각 확인 + 10분마다 잔고 처리 + 고객 메일 자동발송)")
    scheduler.start()


if __name__ == "__main__":
    main()
