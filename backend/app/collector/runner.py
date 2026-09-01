"""수집 파이프라인 오케스트레이션: fetch → map → upsert notice → L1/L2 채점 (U11).

새 소스를 추가할 때 이 파일을 고치지 않아도 되게 하는 게 설계안 04-1의 핵심 원칙이라,
여기는 "openapi 어댑터를 어떻게 조합하는가"만 안다 — 소스별 분기는 source_config에 있다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, insert, select
from sqlalchemy.engine import Connection

from app.collector.adapters.openapi import fetch_openapi_items
from app.collector.mapper import map_item
from app.collector.scorer import L2_PROMOTE_THRESHOLD, passes_l1, score_l2
from app.collector.work_type import guess_work_type
from app.models import notice, notice_score, org, raw_payload, source, source_config, source_credential, source_field_map, source_run

# 공고가 2개월(60일) 넘게 열려있는 경우를 본 적이 없다는 판단(2026-09-01 결정) — 수집 이력이
# 없거나 공백이 이보다 크면 그 이상 과거까지는 훑지 않는다. source_config.config에
# "max_lookback_days"를 두면 소스별로 덮어쓸 수 있다(이 값이 실제와 다른 소스가 나오면).
DEFAULT_MAX_LOOKBACK_DAYS = 60


def _collection_window(conn: Connection, source_id: int, *, max_lookback_days: int) -> tuple[datetime, datetime]:
    """직전 "성공" 수집 시각부터 지금까지. 성공 이력이 없거나 공백이 max_lookback_days를
    넘으면 그만큼만 거슬러 올라간다 — 스케줄러가 오래 멈췄다 재개돼도 무한정 과거까지
    훑지 않으면서, 짧은 간격으로 도는 정상 상황에서는 매번 전체 기간을 재조회하지 않는다.
    """
    now = datetime.now(timezone.utc)
    floor = now - timedelta(days=max_lookback_days)
    last_ok_run_at = conn.execute(
        select(func.max(source_run.c.run_at)).where(source_run.c.source_id == source_id, source_run.c.status == "ok")
    ).scalar_one_or_none()
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


def run_source(conn: Connection, source_id: int, *, max_lookback_days: int = DEFAULT_MAX_LOOKBACK_DAYS) -> dict:
    """소스 하나를 1회 수집한다. 반환값은 결과 요약(로그·테스트 검증용)."""
    src = conn.execute(select(source).where(source.c.id == source_id)).mappings().first()
    if src is None:
        raise ValueError(f"소스를 찾을 수 없습니다: {source_id}")
    if src["adapter_type"] != "openapi":
        raise ValueError(f"U11 범위는 openapi 어댑터만 지원합니다(소스 타입: {src['adapter_type']})")

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

    service_key = conn.execute(
        select(source_credential.c.value).where(
            source_credential.c.source_id == source_id, source_credential.c.kind == "service_key"
        )
    ).scalar_one_or_none()

    effective_max_lookback = cfg["config"].get("max_lookback_days", max_lookback_days)
    begin, end = _collection_window(conn, source_id, max_lookback_days=effective_max_lookback)

    try:
        raw_items = fetch_openapi_items(cfg["config"], service_key, begin=begin, end=end)
    except Exception as exc:  # noqa: BLE001 — 실패도 source_run에 남겨야 "조용한 사망"이 안 됨(CLAUDE.md)
        _record_run(source_id, status="fail", items_fetched=0, error_message=str(exc))
        raise

    conn.execute(
        insert(raw_payload).values(
            source_id=source_id, endpoint=cfg["config"].get("endpoint", ""), body={"items": raw_items}
        )
    )

    inserted = skipped = scored = 0
    l1_ok = passes_l1(conn, source_id)

    for raw_item in raw_items:
        mapped = map_item(raw_item, field_maps)
        if mapped is None:
            skipped += 1
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
                    open_dt=mapped["open_dt"],
                    close_dt=mapped.get("close_dt"),
                    url=mapped["url"],
                ).returning(notice.c.id)
            ).one()
            notice_id = result.id
            inserted += 1

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

    return {"fetched": len(raw_items), "inserted": inserted, "skipped": skipped, "scored": scored}
