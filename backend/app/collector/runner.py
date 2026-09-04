"""수집 파이프라인 오케스트레이션: fetch → map → upsert notice → L1/L2 채점 (U11).

새 소스를 추가할 때 이 파일을 고치지 않아도 되게 하는 게 설계안 04-1의 핵심 원칙이라,
여기는 "openapi 어댑터를 어떻게 조합하는가"만 안다 — 소스별 분기는 source_config에 있다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, insert, select
from sqlalchemy.engine import Connection

from app.collector.adapters.openapi import fetch_openapi_items
from app.collector.mapper import map_item, validate_field_maps
from app.collector.pii import mask_pii
from app.collector.scorer import L2_PROMOTE_THRESHOLD, passes_l1, score_l2
from app.collector.work_type import guess_work_type
from app.models import notice, notice_score, org, raw_payload, source, source_config, source_credential, source_field_map, source_run
from app.services.analysis_pilot import AnalysisInProgressError, UnsupportedSourceError, run_extraction_pilot

# 공고가 2개월(60일) 넘게 열려있는 경우를 본 적이 없다는 판단(2026-09-01 결정) — 수집 이력이
# 없거나 공백이 이보다 크면 그 이상 과거까지는 훑지 않는다. source_config.config에
# "max_lookback_days"를 두면 소스별로 덮어쓸 수 있다(이 값이 실제와 다른 소스가 나오면).
DEFAULT_MAX_LOOKBACK_DAYS = 60


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
    result = conn.execute(insert(org).values(name=name, source_id=source_id).returning(org.c.id)).one()
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


def run_source(
    conn: Connection,
    source_id: int,
    *,
    max_lookback_days: int = DEFAULT_MAX_LOOKBACK_DAYS,
    force: bool = False,
    window: tuple[datetime, datetime] | None = None,
) -> dict:
    """소스 하나를 1회 수집한다. 반환값은 결과 요약(로그·테스트 검증용).

    force=True는 관리자가 수동으로 즉시 재수집할 때만 쓴다 — B등급 최소 수집 간격을 우회한다
    (advisory INBOX #5). 등급 C 차단은 force로도 못 뚫는다 — 활성화 자체가 금지된 소스라서.

    window=(begin, end)는 _collection_window()의 자동 좁히기(직전 성공 시각 기준)를 완전히
    건너뛰고 호출부가 지정한 구간만 그대로 쓴다 — 최초 백필을 하루 단위로 쪼갤 때만 쓰는
    용도다(2026-09-05, 나라장터 입찰공고 30일 일괄 백필이 25페이지 안팎에서 반복적으로
    data.go.kr 타임아웃에 걸려 매번 전량 롤백되는 문제. 한 번에 너무 많은 페이지를 순차
    요청하면서 타임아웃 확률이 누적된 것으로 추정 — 하루씩 나누면 실패해도 그 하루치만 다시
    시도하면 됨). `_last_ok_run_at()`의 run_at은 "실제로 이 명령을 실행한 시각"이라 하루치
    구간을 흉내 낸 값이 아니므로, 자동 좁히기에 맡기면 다음 청크의 begin이 그 하루의 끝이
    아니라 방금 실행한 실제 시각으로 어긋난다 — 그래서 자동 좁히기를 아예 우회한다.
    """
    src = conn.execute(select(source).where(source.c.id == source_id)).mappings().first()
    if src is None:
        raise ValueError(f"소스를 찾을 수 없습니다: {source_id}")
    if src["adapter_type"] != "openapi":
        raise ValueError(f"U11 범위는 openapi 어댑터만 지원합니다(소스 타입: {src['adapter_type']})")
    # 법적 등급 C(금지) — robots 차단 또는 약관상 명시적 금지 소스는 활성화 자체를 거부한다
    # (advisory INBOX #5). 관리자 체크박스가 아니라 여기, 실제 수집이 실행되는 유일한 관문에서
    # 막아야 "체크박스로 우회 못 하는" 강제가 된다.
    if src["legal_tier"] == "C":
        raise ValueError(
            f"'{src['name']}' 소스는 법적 등급 C(수집 금지)입니다 — advisory INBOX #5에 따라 활성화할 수 없습니다."
        )
    if src["legal_tier"] == "B" and not force:
        last_ok = _last_ok_run_at(conn, source_id)
        min_interval = timedelta(minutes=src["frequency_minutes"])
        if last_ok is not None and (datetime.now(timezone.utc) - last_ok) < min_interval:
            raise ValueError(
                f"'{src['name']}'은 법적 등급 B — 최소 수집 간격({src['frequency_minutes']}분) 전입니다 "
                f"(advisory INBOX #5, 마지막 성공 수집: {last_ok.isoformat()})."
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

    try:
        raw_items = fetch_openapi_items(cfg["config"], service_key, begin=begin, end=end)
    except Exception as exc:  # noqa: BLE001 — 실패도 source_run에 남겨야 "조용한 사망"이 안 됨(CLAUDE.md)
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

    inserted = skipped = scored = out_of_window = already_closed = auto_extracted = 0
    l1_ok = passes_l1(conn, source_id)
    now = datetime.now(timezone.utc)

    for raw_item in raw_items:
        mapped = map_item(raw_item, field_maps)
        if mapped is None:
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

            # 2026-09-05 — S8 파일럿(첨부문서 다운로드+텍스트 추출) 자동 실행. 관리자가 이
            # 소스에서 명시적으로 켜둔 경우에만 동작한다(source.auto_extract) — CLAUDE.md S8
            # 원칙 3("자동 실행 금지")과 충돌하지 않는 이유는 시스템이 알아서 트는 게 아니라
            # 관리자가 미리 정해둔 설정이기 때문. IRIS만 기본으로 켜져 있고(물량이 적음),
            # 나라장터처럼 물량이 많은 소스는 기본 꺼짐 — 실수로 켜져도 지원 안 하는 URL은
            # UnsupportedSourceError로 조용히 건너뛴다. 실패해도 수집 자체는 계속돼야 하므로
            # 예외를 여기서 삼킨다(개별 공고 분석 실패가 전체 수집을 막으면 안 됨).
            if src["auto_extract"]:
                try:
                    run_extraction_pilot(conn, notice_id)
                    auto_extracted += 1
                except (AnalysisInProgressError, UnsupportedSourceError):
                    pass
                except Exception:  # noqa: BLE001 — 조용히 삼키지만 개별 공고 건이라 수집 자체엔 지장 없음
                    pass

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

    _record_run(source_id, status="ok", items_fetched=len(raw_items))

    return {
        "fetched": len(raw_items),
        "inserted": inserted,
        "skipped": skipped,
        "scored": scored,
        "out_of_window": out_of_window,
        "already_closed": already_closed,
        "auto_extracted": auto_extracted,
    }
