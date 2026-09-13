"""수집 파이프라인 오케스트레이션: fetch → map → upsert notice → L1/L2 채점 (U11).

같은 어댑터 타입의 소스를 추가할 때 이 파일을 고치지 않아도 되게 하는 게 설계안 04-1의 핵심
원칙이라, 여기는 "어댑터가 무엇을 돌려주는가"만 안다 — 소스별 필드 매핑은 source_config·
source_field_map에 있다. 어댑터 타입 자체(openapi/html)는 두 종류뿐이라 여기서 분기하지만,
같은 타입 안에서 소스가 늘어나는 것(예: 나라장터 API가 하나 더 생김)은 config만 추가하면 된다
(2026-09-13 html 어댑터 도입, app/collector/adapters/html.py 참고 — 공공데이터포털 API가
없는 자체 전자조달 사이트를 위한 것)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Connection

from app.collector.adapters.html import fetch_html_items
from app.collector.adapters.openapi import fetch_openapi_items
from app.collector.mapper import map_item, validate_field_maps
from app.collector.pii import mask_pii
from app.collector.scorer import L2_PROMOTE_THRESHOLD, passes_l1, score_l2
from app.collector.work_type import guess_work_type
from app.db import engine
from app.models import notice, notice_score, org, raw_payload, source, source_config, source_credential, source_field_map, source_run
from app.services.notice_cleanup import delete_expired_notices
from app.services.notice_dedup import find_and_mark_superseded
from app.services.org_classification import classify_org_category
from app.services.pending_analysis import process_new_notices

# 공고가 2개월(60일) 넘게 열려있는 경우를 본 적이 없다는 판단(2026-09-01 결정) — 수집 이력이
# 없거나 공백이 이보다 크면 그 이상 과거까지는 훑지 않는다. source_config.config에
# "max_lookback_days"를 두면 소스별로 덮어쓸 수 있다(이 값이 실제와 다른 소스가 나오면).
DEFAULT_MAX_LOOKBACK_DAYS = 60

# "지금 수집" 버튼을 누른 뒤 페이지를 벗어났다 돌아오면 이미 끝난 것처럼 보이는 문제(2026-09-08
# 사용자 발견) — source_run에 시작 시점부터 'running' 행을 남겨 진행 여부를 서버 상태로
# 조회 가능하게 한다. 하트비트가 없어(동기 실행이라 "살아있다"를 별도로 알릴 수단이 없음)
# 프로세스가 죽으면 이 행이 영원히 'running'으로 남을 수 있다 — 이 시간을 넘기면 죽은 것으로
# 보고 다음 시도를 허용한다(list_sources()도 표시할 때 같은 기준을 쓴다).
RUNNING_STALE_MINUTES = 60


class CollectionInProgressError(Exception):
    """동일 소스에 이미 진행 중인 수집이 있음 — 중복 실행 거부(S8 원칙 3과 같은 취지)."""


def _last_ok_run_at(conn: Connection, source_id: int) -> datetime | None:
    return conn.execute(
        select(func.max(source_run.c.run_at)).where(source_run.c.source_id == source_id, source_run.c.status == "ok")
    ).scalar_one_or_none()


def _collection_window(conn: Connection, source_id: int, *, max_lookback_days: int) -> tuple[datetime, datetime]:
    """직전 "성공" 수집 시각부터 지금까지. 성공 이력이 없거나 공백이 max_lookback_days를
    넘으면 그만큼만 거슬러 올라간다 — 스케줄러가 오래 멈췄다 재개돼도 무한정 과거까지
    훑지 않으면서, 짧은 간격으로 도는 정상 상황에서는 매번 전체 기간을 재조회하지 않는다.
    """
    now = datetime.now(timezone.utc)
    floor = now - timedelta(days=max_lookback_days)
    last_ok_run_at = _last_ok_run_at(conn, source_id)
    if last_ok_run_at is None:
        return floor, now
    # API 응답 지연·시계 오차로 직전 조회 경계에 걸친 공고를 놓치지 않도록 1시간 겹쳐서 조회
    begin = last_ok_run_at - timedelta(hours=1)
    return max(begin, floor), now


def _get_or_create_org(conn: Connection, name: str, source_id: int) -> int:
    row = conn.execute(select(org.c.id).where(org.c.name == name)).first()
    if row:
        return row[0]
    # 새로 발견되는 발주기관은 지금 수집 중인 소스(공고기관/채널)를 그대로 연결해둔다 —
    # 관리자 페이지 "소스 관리"(발주기관 중심 목록)가 별도 수작업 없이 채워지도록.
    # category(업종/분야)는 2026-09-11까지 여기서 아예 설정을 안 해서 실제 수집 데이터
    # 2,981건 중 2건만 채워져 있었다(발견) — 기관명 패턴 분류를 신규 생성 시점에도 적용한다.
    result = conn.execute(
        insert(org).values(name=name, source_id=source_id, category=classify_org_category(name)).returning(org.c.id)
    ).one()
    return result.id


def _record_run(source_id: int, *, status: str, items_fetched: int, error_message: str | None = None) -> None:
    """호출부의 conn/트랜잭션과 **독립적으로** 커밋한다. run_source가 실패해서 호출부 트랜잭션이
    통째로 롤백되더라도, "시도했고 실패했다"는 기록 자체는 남아야 한다 — 안 그러면 소스가
    조용히 죽어도 아무도 모른다(CLAUDE.md "HTML 소스 조용한 사망" 리스크와 같은 이유)."""
    from app.db import engine as _engine

    with _engine.begin() as log_conn:
        log_conn.execute(
            insert(source_run).values(
                source_id=source_id, status=status, items_fetched=items_fetched, error_message=error_message
            )
        )


def _start_run(source_id: int) -> int:
    """새 수집 시도를 'running'으로 남기고 id를 반환한다. 호출부 트랜잭션과 독립적으로 즉시
    커밋해야 다른 요청이 곧바로 "진행 중"임을 볼 수 있다(동시 실행 방지·프론트 상태 표시 목적,
    2026-09-08)."""
    from app.db import engine as _engine

    with _engine.begin() as log_conn:
        return log_conn.execute(
            insert(source_run).values(source_id=source_id, status="running", items_fetched=0).returning(source_run.c.id)
        ).scalar_one()


def _finish_run(run_id: int, *, status: str, items_fetched: int, error_message: str | None = None) -> None:
    from app.db import engine as _engine

    with _engine.begin() as log_conn:
        log_conn.execute(
            update(source_run)
            .where(source_run.c.id == run_id)
            .values(status=status, items_fetched=items_fetched, error_message=error_message)
        )


def _reject_if_already_running(source_id: int) -> None:
    """이 소스에 이미 'running' 행이 있으면 거부한다. RUNNING_STALE_MINUTES를 넘겼으면 이전
    시도가 비정상 종료(프로세스 강제 종료 등)된 것으로 보고 실패로 마감한 뒤 새 시도를
    허용한다 — 하트비트가 없어 그 외엔 살았는지 죽었는지 알 방법이 없다."""
    with engine.connect() as conn:
        row = conn.execute(
            select(source_run.c.id, source_run.c.run_at)
            .where(source_run.c.source_id == source_id, source_run.c.status == "running")
            .order_by(source_run.c.id.desc())
            .limit(1)
        ).first()
    if row is None:
        return
    run_id, run_at = row
    if datetime.now(timezone.utc) - run_at < timedelta(minutes=RUNNING_STALE_MINUTES):
        raise CollectionInProgressError(f"이미 수집이 진행 중입니다(시작: {run_at.isoformat()}).")
    _finish_run(
        run_id, status="fail", items_fetched=0,
        error_message=f"{RUNNING_STALE_MINUTES}분 넘게 응답이 없어 중단된 것으로 처리(프로세스 비정상 종료 추정)",
    )


def run_source(
    conn: Connection,
    source_id: int,
    *,
    max_lookback_days: int = DEFAULT_MAX_LOOKBACK_DAYS,
    window: tuple[datetime, datetime] | None = None,
    run_id: int | None = None,
) -> dict:
    """소스 하나를 1회 수집한다. 반환값은 결과 요약(로그·테스트 검증용).

    window=(begin, end)는 _collection_window()의 자동 좁히기(직전 성공 시각 기준)를 완전히
    건너뛰고 호출부가 지정한 구간만 그대로 쓴다 — 최초 백필을 하루 단위로 쪼갤 때만 쓰는
    용도다(2026-09-05, 나라장터 입찰공고 30일 일괄 백필이 25페이지 안팎에서 반복적으로
    data.go.kr 타임아웃에 걸려 매번 전량 롤백되는 문제. 한 번에 너무 많은 페이지를 순차
    요청하면서 타임아웃 확률이 누적된 것으로 추정 — 하루씩 나누면 실패해도 그 하루치만 다시
    시도하면 됨). `_last_ok_run_at()`의 run_at은 "실제로 이 명령을 실행한 시각"이라 하루치
    구간을 흉내 낸 값이 아니므로, 자동 좁히기에 맡기면 다음 청크의 begin이 그 하루의 끝이
    아니라 방금 실행한 실제 시각으로 어긋난다 — 그래서 자동 좁히기를 아예 우회한다.

    run_id(2026-09-08)는 run_source_and_process_pending()이 미리 만들어둔 'running' 행의
    id다 — 주어지면 그 행을 갱신하고(성공 시엔 A1/A2까지 끝난 뒤 호출부가 최종 마감하도록
    일부러 여기선 'ok'로 안 바꾼다), 안 주어지면(테스트·CLI에서 run_source를 직접 부르는
    경우) 예전처럼 이 함수가 직접 새 행을 남긴다.
    """
    src = conn.execute(select(source).where(source.c.id == source_id)).mappings().first()
    if src is None:
        raise ValueError(f"소스를 찾을 수 없습니다: {source_id}")
    if src["adapter_type"] not in ("openapi", "html"):
        raise ValueError(f"지원하지 않는 어댑터 타입입니다: {src['adapter_type']}")
    # 공고 자동 수집 on/off(2026-09-05, 관리자 화면 토글) — 관리자가 의도적으로 끈 소스는
    # 관리자 화면에서 다시 켜기 전엔 우회할 방법이 없다(법적 등급 C와 같은 성격 — 명시적 배제).
    if not src["active"]:
        raise ValueError(f"'{src['name']}' 소스는 비활성화 상태입니다 — 관리자 화면(데이터 수집채널)에서 켜야 수집할 수 있습니다.")
    # 법적 등급 C(금지) — robots 차단 또는 약관상 명시적 금지 소스는 활성화 자체를 거부한다
    # (advisory INBOX #5). 관리자 체크박스가 아니라 여기, 실제 수집이 실행되는 유일한 관문에서
    # 막아야 "체크박스로 우회 못 하는" 강제가 된다.
    if src["legal_tier"] == "C":
        raise ValueError(
            f"'{src['name']}' 소스는 법적 등급 C(수집 금지)입니다 — advisory INBOX #5에 따라 활성화할 수 없습니다."
        )
    cfg = conn.execute(
        select(source_config)
        .where(source_config.c.source_id == source_id)
        .order_by(source_config.c.ver.desc())
        .limit(1)
    ).mappings().first()
    if cfg is None:
        raise ValueError("source_config가 없습니다 — 소스 등록이 완료되지 않았습니다.")

    field_maps = [
        dict(row)
        for row in conn.execute(
            select(source_field_map.c.target_field, source_field_map.c.source_path, source_field_map.c.format_hint).where(
                source_field_map.c.source_config_id == cfg["id"]
            )
        ).mappings()
    ]
    validate_field_maps(field_maps, legal_tier=src["legal_tier"])

    service_key = conn.execute(
        select(source_credential.c.value).where(
            source_credential.c.source_id == source_id, source_credential.c.kind == "service_key"
        )
    ).scalar_one_or_none()

    if window is not None:
        begin, end = window
    else:
        effective_max_lookback = cfg["config"].get("max_lookback_days", max_lookback_days)
        begin, end = _collection_window(conn, source_id, max_lookback_days=effective_max_lookback)

    fetch_items = fetch_openapi_items if src["adapter_type"] == "openapi" else fetch_html_items
    try:
        raw_items = fetch_items(cfg["config"], service_key, begin=begin, end=end)
    except Exception as exc:  # noqa: BLE001 — 실패도 source_run에 남겨야 "조용한 사망"이 안 됨(CLAUDE.md)
        if run_id is not None:
            _finish_run(run_id, status="fail", items_fetched=0, error_message=str(exc))
        else:
            _record_run(source_id, status="fail", items_fetched=0, error_message=str(exc))
        raise

    # 담당자 개인정보 마스킹(advisory INBOX #8) — raw_payload는 "원본 보존"이 원칙이나 개인정보는
    # 예외. field_maps가 이런 필드를 안 쓰더라도(현재 다 그렇다) 저장 자체를 막아야 안전하므로,
    # 여기서 한 번 마스킹한 값을 raw_payload 저장과 매핑 양쪽에 그대로 쓴다.
    raw_items = mask_pii(raw_items)

    conn.execute(
        insert(raw_payload).values(
            source_id=source_id, endpoint=cfg["config"].get("endpoint", ""), body={"items": raw_items}
        )
    )

    inserted = skipped = scored = out_of_window = already_closed = 0
    # 이번 실행에서 새로 들어온 공고 id만 따로 기억해둔다(2026-09-07 사용자 지시) — 첨부분석
    # (A1)·AI분석(A2)이 오래된 미처리 잔고에 밀려 정작 방금 수집한 건은 처리 안 되는 문제가
    # 있었다. run_source_and_process_pending()이 이 목록만 콕 집어 바로 처리한다.
    inserted_notice_ids: list[int] = []
    # 방금 수집한 원본 API 항목을 notice_id별로 남겨둔다(2026-09-08 사용자 지시) — 첨부분석
    # (A1)이 g2b 계열에서 이미 받아둔 이 데이터를 공고 한 건마다 또 실시간 재조회하고 있었다
    # (사전규격 223건 수집 시 223번 재호출) — 느리고, apis.data.go.kr이 불안정한 날엔 재조회
    # 다수가 조용히 실패해 "첨부 없음"으로 잘못 기록되는 사고로 이어졌다(실제 수집 결과로 확인).
    inserted_raw_items: dict[int, dict] = {}
    l1_ok = passes_l1(conn, source_id)
    now = datetime.now(timezone.utc)

    for raw_item in raw_items:
        mapped = map_item(raw_item, field_maps)
        if mapped is None:
            skipped += 1
            continue
        # IRIS(rcveSttSeNmLst="접수상태구분명")는 "미게시"(테스트 항목·이미 선정된 다년도
        # 과제의 연차/단계 실적보고서 접수처럼 신규 공모가 아닌 내부 행정 게시물) 상태의 항목도
        # 같은 목록 API에 섞어 준다(2026-09-05 발견 — IRIS 접수예정 대량 재수집 153건 중 143건이
        # open_dt조차 없는 "미게시"였고, 실제 사이트 화면엔 그보다 훨씬 적게 보임). "공고예고"·
        # "공고접수중"(단일 상태) 외에는(이미 마감된 조합 포함) 신규 지원기회로 볼 수 없어 건너뛴다.
        rcve_status = (mapped.get("extra") or {}).get("rcveSttSeNmLst")
        if rcve_status is not None and rcve_status not in ("공고예고", "공고접수중"):
            skipped += 1
            continue
        # 날짜범위 파라미터를 안 받는 API(IRIS 등, pagination만 있고 date_range_params가 없는
        # 소스)는 서버가 기간을 안 걸러주므로 여기서 직접 자른다 — begin은 이미
        # _collection_window()가 계산해둔 값(2026-09-02, IRIS 2개월치 재수집 정확도 개선).
        # open_dt가 없는 소스(2026-09-05, open_dt를 필수에서 뺌)는 판단 근거가 없어 대상 아님.
        open_dt = mapped.get("open_dt")
        if open_dt is not None and open_dt < begin:
            out_of_window += 1
            continue
        # 2026-09-04 — 나라장터는 공고 "게시일" 기준으로만 기간을 걸러줘서 이미 마감된 공고도
        # 그대로 들어온다(실측: 용역 5,000건 중 82%가 이미 마감). BidRadar 취지("이미 늦기
        # 전에 본다")상 이미 마감된 건 참여 판단에 쓸모가 없어 수집 단계에서부터 제외한다.
        # close_dt가 없는 소스(IRIS·과기정통부 등, INBOX #1)는 "마감됐다"고 판단할 근거가
        # 없으므로 대상이 아니다.
        close_dt = mapped.get("close_dt")
        if close_dt is not None and close_dt < now:
            already_closed += 1
            continue

        org_id = _get_or_create_org(conn, mapped["org_name"], source_id) if mapped.get("org_name") else None
        existing = conn.execute(select(notice.c.id).where(notice.c.url == mapped["url"])).first()
        if existing:
            notice_id = existing[0]
        else:
            result = conn.execute(
                insert(notice).values(
                    source_id=source_id,
                    source_ver=cfg["ver"],
                    notice_no=mapped.get("notice_no"),
                    stage=src["stage"],
                    biz_type=cfg["config"].get("biz_type"),
                    work_type=guess_work_type(mapped["title"]),
                    title=mapped["title"],
                    org_id=org_id,
                    est_price=mapped.get("est_price"),
                    region=mapped.get("region"),
                    open_dt=open_dt,
                    close_dt=mapped.get("close_dt"),
                    url=mapped["url"],
                    extra=mapped.get("extra"),
                ).returning(notice.c.id)
            ).one()
            notice_id = result.id
            inserted += 1
            inserted_notice_ids.append(notice_id)
            inserted_raw_items[notice_id] = raw_item
            # 2026-09-05부터 — 첨부문서 자동 추출(A1)·AI 자동분석(A2)은 이 함수(목록 수집)에서
            # 분리했다(app/services/pending_analysis.py). 이유: 전에는 여기서 신규 공고마다
            # 첨부파일을 동기로 다운로드했는데, 첫 백필처럼 신규 건이 수백 개면 그 다운로드들이
            # 전부 이 함수 하나의(호출부가 감싼) 트랜잭션 안에 들어가 오래 열려있게 되고, 그
            # 트랜잭션이 잡은 락이 다른 작업(예: 스키마 마이그레이션)까지 막는 사고가 실제로
            # 발생했다. 이제 목록 수집은 빠르게 끝내고 커밋하며, 첨부 추출·AI분석은 후속 패스가
            # 공고마다 각각 짧은 트랜잭션으로 처리한다.

        if not l1_ok:
            continue

        for topic_id, info in score_l2(conn, mapped["title"]).items():
            if info["score"] < L2_PROMOTE_THRESHOLD:
                continue
            conn.execute(
                insert(notice_score).values(
                    notice_id=notice_id,
                    interest_topic_id=topic_id,
                    l2_score=info["score"],
                    reason=f"키워드 매칭: {', '.join(info['matched_terms'])}",
                    rule_ver=1,
                )
            )
            scored += 1

    if run_id is None:
        _record_run(source_id, status="ok", items_fetched=len(raw_items))
    # run_id가 있으면 여기서 'ok'로 확정하지 않는다 — 호출부(run_source_and_process_pending)가
    # 첨부분석·AI분석까지 끝난 뒤 최종 마감한다(그래야 A1/A2가 도는 동안에도 "진행 중"으로
    # 보인다).

    # 동일 발주기관+동일 사업명이 발주계획/사전규격/입찰공고 단계로 나뉘어 수집되는 경우가
    # 매 수집마다 꽤 발생해(2026-09-06 사용자 지시) 수동 실행만으로는 부족하다고 판단 —
    # 키워드 재스캔(수정이 드묾)과 달리 이건 매 수집 직후 자동으로 재계산한다. 소스와 무관하게
    # 전체 공고를 다시 훑는 멱등 함수라 특정 소스만 위해 분기하지 않아도 된다(설계안 04-1).
    dedup_result = find_and_mark_superseded(conn)

    # 오래된 공고 자동 삭제(2026-09-10 사용자 지시 — "오래된 데이터는 자동으로 삭제되어야
    # 한다"). 스케줄러 인프라가 아직 없어(구현스펙 참고) 정해진 시각에 도는 별도 잡을 만들 수
    # 없으므로, 대신 dedup과 같은 자리에서 "수집이 실행될 때마다" 같이 돈다 — 소스와 무관한
    # 전체 정리이므로 여기 한 번만 있으면 된다(app/services/notice_cleanup.py 참고).
    delete_expired_notices(conn)

    return {
        "fetched": len(raw_items),
        "inserted": inserted,
        "skipped": skipped,
        "scored": scored,
        "out_of_window": out_of_window,
        "already_closed": already_closed,
        "dedup_groups_with_duplicates": dedup_result["groups_with_duplicates"],
        "dedup_notices_updated": dedup_result["notices_updated"],
        "inserted_notice_ids": inserted_notice_ids,
        "inserted_raw_items": inserted_raw_items,
    }


def run_source_and_process_pending(
    source_id: int,
    *,
    max_lookback_days: int = DEFAULT_MAX_LOOKBACK_DAYS,
) -> dict:
    """파이프라인 전체(수집→중복체크→첨부분석(A1)→AI분석(A2))를 한 번에 잇는다(2026-09-07
    사용자 지시) — "자동수집"이든 "지금 수집"이든 이 함수를 거쳐야 끝까지 이어진다.

    run_source()의 트랜잭션이 완전히 커밋된 **뒤**에 이어서 처리한다 — A1이 공고마다 첨부파일을
    내려받는 동안 수집 트랜잭션의 락을 계속 쥐고 있으면 다른 작업(스키마 마이그레이션 등)을
    막는 사고가 났던 전례(2026-09-05)와 같은 이유로, 절대 같은 트랜잭션 안에서 잇지 않는다.

    이번에 새로 수집된 공고만 콕 집어 처리한다(process_new_notices, 2026-09-07 사용자 지시) —
    이 소스에 첨부분석을 아직 안 한 오래된 잔고가 아무리 많이 쌓여 있어도(실측: 한 소스에
    2천 건 넘게 쌓여있던 사례), 방금 수집한 건은 그 잔고 순서를 기다리지 않고 바로 분석된다.
    오래된 잔고 자체를 처리하려면 여전히 관리자가 수동으로 process-pending을 돌려야 한다.
    첨부분석·AI분석은 각 소스의 auto_extract/auto_analyze 설정을 그대로 따른다(사용자 지시).

    2026-09-08 — 이 함수가 실행되는 동안 source_run에 'running' 행을 남겨 관리자 화면이
    "수집 중"을 실시간으로 보여줄 수 있게 한다(사용자 발견: "지금 수집" 클릭 후 다른 메뉴로
    갔다 돌아오면 이미 끝난 것처럼 보이는 문제 — 브라우저 쪽 로딩 상태만으로는 새로고침·다른
    탭에서 알 수 없었음). 동일 소스에 이미 진행 중인 시도가 있으면 CollectionInProgressError로
    거부한다(S8 원칙 3과 같은 취지)."""
    _reject_if_already_running(source_id)
    run_id = _start_run(source_id)
    try:
        with engine.begin() as conn:
            collect_result = run_source(conn, source_id, max_lookback_days=max_lookback_days, run_id=run_id)
        new_notice_ids = collect_result.pop("inserted_notice_ids")
        raw_items_by_notice_id = collect_result.pop("inserted_raw_items")
        pending_result = process_new_notices(source_id, new_notice_ids, raw_items_by_notice_id=raw_items_by_notice_id)
    except Exception as exc:  # noqa: BLE001 — 실패도 반드시 마감해야 "진행 중"에 영원히 안 갇힘
        _finish_run(run_id, status="fail", items_fetched=0, error_message=str(exc))
        raise
    _finish_run(run_id, status="ok", items_fetched=collect_result["fetched"])
    return {**collect_result, **pending_result}
