"""python -m app.cli seed 가 호출하는 시드 데이터. 11절 — "빈 화면으로 개발하면 레이아웃이
틀어진다." 전 테이블(30개)에 최소 1행 이상 들어가야 U2 완료조건을 만족한다.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine, insert, select

from app.models import (
    analysis,
    analysis_check,
    analysis_doc,
    analysis_flag,
    analysis_requirement,
    audit_log,
    award,
    classification_correction,
    customer,
    customer_followed_org,
    customer_interest,
    customer_interest_term,
    interest_topic,
    keyword_rule,
    notice,
    notice_score,
    notice_version,
    org,
    product,
    product_cert,
    product_reference,
    product_spec,
    raw_payload,
    requirement,
    source,
    source_config,
    source_credential,
    source_field_map,
    source_run,
)
from app.seed_constants import (
    ATTRIBUTION_TEXT,
    AUTO_EXTRACT_SOURCES,
    INTEREST_TOPICS,
    KEYWORD_SEED,
    NOTICE_TITLE_TEMPLATES,
    ORG_SEED,
    PIPELINE_STAGES,
    REAL_OPENAPI_CONFIG,
    SOURCE_SEED,
    STAGES,
)
from app.services.source_registry import derive_channel_name

_RNG = random.Random(42)  # 재현 가능한 시드


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_seed(engine: Engine) -> None:
    with engine.begin() as conn:
        topic_ids = _seed_topics(conn)
        customer_ids = _seed_customers(conn, topic_ids)
        # 소스를 발주기관보다 먼저 시드해야 한다 — org.source_id가 어느 채널로 수집되는지
        # 가리키므로(관리자 페이지 "소스 관리" 발주기관 목록용), 참조 대상이 먼저 있어야 함.
        source_ids, source_config_ids = _seed_sources(conn)
        source_id_by_name = dict(zip((s[0] for s in SOURCE_SEED), source_ids))
        org_ids = _seed_orgs(conn, source_id_by_name)
        _seed_source_runs(conn, source_ids)
        _seed_raw_payloads(conn, source_ids)
        notice_ids = _seed_notices(conn, source_ids, org_ids)
        _seed_notice_extras(conn, notice_ids, topic_ids)
        _seed_awards(conn, notice_ids, org_ids)
        _seed_customer_extras(conn, customer_ids, org_ids)
        product_ids = _seed_products(conn, customer_ids["(주)그립"])
        _seed_analyses(conn, notice_ids, product_ids)
        _seed_audit_log(conn, source_ids)


def run_seed_prod(engine: Engine) -> None:
    """prod 전용 최소 시드(2026-09-10, 사용자 지시 — "기업 관리 부분은 비워둬, 내가 직접
    채울꺼고"). run_seed()는 U2("빈 화면으로 개발하면 레이아웃이 틀어진다") 목적의 로컬 개발용
    데모 픽스처라 가짜 고객("(주)그립" 1건)·가짜 공고·가짜 낙찰·가짜 제품·가짜 분석까지 전부
    같이 만든다 — prod에 그대로 실행하면 이 데모 데이터가 실제 화면에 섞여 나온다.

    prod가 실제로 필요한 건 수집 파이프라인이 돌아가는 데 필요한 참조 데이터뿐이다:
    관심주제·키워드 규칙(_seed_topics), 소스·소스설정·필드매핑(_seed_sources, 실제 운영
    OpenAPI 설정), 발주기관(_seed_orgs). 고객(customer)은 하나도 만들지 않는다 — 사용자가
    관리자 화면에서 그립(AI/IoT/Robot)·그립(Safety/Factory)·그립(AX/Service) 3개 기관으로
    직접 등록할 계획이다.
    """
    with engine.begin() as conn:
        _seed_topics(conn)
        source_ids, _source_config_ids = _seed_sources(conn)
        source_id_by_name = dict(zip((s[0] for s in SOURCE_SEED), source_ids))
        _seed_orgs(conn, source_id_by_name)


def _seed_topics(conn) -> dict[str, int]:
    ids: dict[str, int] = {}
    # 번호는 1부터 시작(2026-09-02 요청) — 관리자 화면에 "0번"이 보이면 사람이 세는 방식과
    # 어긋나 혼란스럽다는 지적.
    for i, name in enumerate(INTEREST_TOPICS, start=1):
        row = conn.execute(
            insert(interest_topic).values(name=name, sort_order=i, active=True).returning(interest_topic.c.id)
        ).one()
        ids[name] = row.id
    for topic_name, terms in KEYWORD_SEED.items():
        for term, weight_class, weight in terms:
            conn.execute(
                insert(keyword_rule).values(
                    interest_topic_id=ids[topic_name], term=term, weight_class=weight_class, weight=weight,
                )
            )
    return ids


def _seed_customers(conn, topic_ids: dict[str, int]) -> dict[str, int]:
    # 2026-09-05까지는 "예시고객 A/B"라는 가짜 예시 고객도 시드했었는데(빈 상태·격리 테스트용),
    # 사용자 지시로 제거 — 실제 고객이 생기기 전까지는 "(주)그립" 하나만으로 충분하고, 가짜
    # 데이터가 실제 관리 화면에 계속 보이는 게 오히려 혼란스럽다.
    rows = [
        {"name": "(주)그립", "plan_tier": "internal", "contact_email": "report@grib.co.kr"},
    ]
    ids: dict[str, int] = {}
    for row in rows:
        result = conn.execute(insert(customer).values(**row).returning(customer.c.id)).one()
        ids[row["name"]] = result.id

    for topic_name in ("산업안전/CCTV·영상보안", "스마트교육/에듀테크", "IoT/센서"):
        conn.execute(
            insert(customer_interest).values(customer_id=ids["(주)그립"], interest_topic_id=topic_ids[topic_name])
        )
    return ids


def _seed_orgs(conn, source_id_by_name: dict[str, int]) -> list[int]:
    ids = []
    for i, (name, abbr, category, source_name, notice_url) in enumerate(ORG_SEED):
        row = conn.execute(
            insert(org).values(
                name=name, code=f"ORG{i:03d}", category=category, abbr=abbr, notice_url=notice_url,
                source_id=source_id_by_name.get(source_name) if source_name else None,
            ).returning(org.c.id)
        ).one()
        ids.append(row.id)
    return ids


def _seed_one_source(conn, seed_row: tuple) -> tuple[int, int]:
    """SOURCE_SEED 한 행을 실제로 insert한다(source+source_config+source_field_map+
    source_credential) — _seed_sources()(전체 시드)와 add_source()(운영 DB에 소스 하나만
    추가, 2026-09-13 신설) 둘 다 이 함수를 공유한다."""
    (
        name, org_name, url, homepage_url, stage, adapter, is_system, skip_l1, frequency_minutes,
        legal_tier, license_note, license_evidence_url,
    ) = seed_row

    row = conn.execute(
        insert(source).values(
            name=name, org_name=org_name, channel_name=derive_channel_name(name, org_name),
            base_url=url, homepage_url=homepage_url,
            stage=stage, adapter_type=adapter,
            frequency_minutes=frequency_minutes, is_system=is_system, skip_l1=skip_l1, active=True,
            legal_tier=legal_tier, license_note=license_note, license_evidence_url=license_evidence_url,
            # 시드 시점을 "확인 시각"으로 남긴다 — 실제 운영에서는 INBOX #6 준법 재확인 도구가
            # robots.txt를 다시 읽어 이 값을 갱신한다(app/collector/compliance.py).
            legal_verified_at=_now(),
            attribution_text=ATTRIBUTION_TEXT.get(name),
            auto_extract=name in AUTO_EXTRACT_SOURCES,
        ).returning(source.c.id)
    ).one()

    real = REAL_OPENAPI_CONFIG.get(name)
    config = real["config"] if real else {"adapter": adapter, "endpoint": url}

    cfg_row = conn.execute(
        insert(source_config).values(
            source_id=row.id, ver=1, config=config, created_by="report@grib.co.kr",
        ).returning(source_config.c.id)
    ).one()

    field_maps = real["field_maps"] if real else [
        ("title", "$.title", None), ("org_name", "$.org", None),
        ("open_dt", "$.openDate", None), ("url", "$.url", None),
    ]
    for target_field, path, format_hint in field_maps:
        conn.execute(
            insert(source_field_map).values(
                source_config_id=cfg_row.id, target_field=target_field, source_path=path, format_hint=format_hint,
            )
        )

    # 실제 인증키는 infra/.env의 DATA_GO_KR_SERVICE_KEY를 통해 별도로 넣는다(U13에서 관리자
    # 화면으로 대체 예정) — 시드는 자리표시자만 넣어 "인증키 없음" 상태를 명시적으로 남긴다.
    # html 어댑터(서비스키 자체가 없는 사이트 스크레이핑)에도 그냥 넣어둔다 — source_credential이
    # 있어야 하느냐 없느냐로 어댑터 종류를 구분하는 코드가 없어, 없으면 오히려 조회 쪽에서
    # "일부 소스만 행이 없음"이라는 특이 케이스가 생긴다.
    conn.execute(insert(source_credential).values(source_id=row.id, kind="service_key", value="__NOT_SET__"))

    return row.id, cfg_row.id


def _seed_sources(conn) -> tuple[list[int], list[int]]:
    source_ids: list[int] = []
    config_ids: list[int] = []
    for seed_row in SOURCE_SEED:
        source_id, config_id = _seed_one_source(conn, seed_row)
        source_ids.append(source_id)
        config_ids.append(config_id)
    return source_ids, config_ids


def add_source(engine: Engine, name: str) -> int:
    """이미 운영 중인 DB(prod 포함)에 SOURCE_SEED·REAL_OPENAPI_CONFIG에 정의된 소스를 하나만
    추가한다(2026-09-13, 국가철도공단 추가 건 — seed-prod를 통째로 다시 돌리면 기존 15개
    소스가 전부 중복 생성되므로, 한 건만 안전하게 추가할 방법이 없었다). name은 SOURCE_SEED의
    소스명과 정확히 일치해야 한다. 이미 같은 이름의 소스가 있으면 거부한다(CLAUDE.md "기존 행
    덮어쓰기 금지"와 같은 취지 — 실수로 두 번 추가하면 중복 수집이 된다)."""
    seed_row = next((row for row in SOURCE_SEED if row[0] == name), None)
    if seed_row is None:
        raise ValueError(f"SOURCE_SEED에 없는 소스명입니다: {name!r} — 먼저 app/seed_constants.py에 추가하세요.")

    with engine.begin() as conn:
        existing = conn.execute(select(source.c.id).where(source.c.name == name)).first()
        if existing:
            raise ValueError(f"이미 존재하는 소스입니다(id={existing[0]}): {name!r}")
        source_id, _config_id = _seed_one_source(conn, seed_row)
    return source_id


def _seed_source_runs(conn, source_ids: list[int]) -> None:
    statuses = ["ok", "ok", "ok", "warn", "fail", "inactive"]
    for source_id in source_ids:
        for day in range(30):
            run_at = _now() - timedelta(days=day)
            status = _RNG.choice(statuses)
            conn.execute(
                insert(source_run).values(
                    source_id=source_id, run_at=run_at, status=status,
                    items_fetched=0 if status in ("fail", "inactive") else _RNG.randint(0, 15),
                    duration_ms=_RNG.randint(200, 4000),
                    error_message="타임아웃" if status == "fail" else None,
                )
            )


def _seed_raw_payloads(conn, source_ids: list[int]) -> None:
    for source_id in source_ids:
        for _ in range(3):
            conn.execute(
                insert(raw_payload).values(
                    source_id=source_id, endpoint="https://example.grib-test.kr/notices",
                    body={"seed": True, "items": []},
                )
            )


def _seed_notices(conn, source_ids: list[int], org_ids: list[int]) -> list[int]:
    ids: list[int] = []
    for i in range(120):
        org_name_pick = _RNG.choice([o[0] for o in ORG_SEED])
        title_template, biz_type, work_type = _RNG.choice(NOTICE_TITLE_TEMPLATES)
        title = title_template.format(org=org_name_pick)
        open_dt = _now() - timedelta(days=_RNG.randint(0, 20))
        close_dt = _now() + timedelta(days=_RNG.randint(-1, 30))
        row = conn.execute(
            insert(notice).values(
                source_id=_RNG.choice(source_ids),
                source_ver=1,
                notice_no=f"SEED-{i:04d}",
                ord=0,
                stage=_RNG.choice(STAGES),
                biz_type=biz_type,
                work_type=work_type,
                title=title,
                org_id=_RNG.choice(org_ids),
                est_price=_RNG.randint(3_000, 500_000) * 10_000,
                region="전국",
                open_dt=open_dt,
                close_dt=close_dt,
                url=f"https://www.g2b.go.kr/notice/{i:04d}",
                pipeline_stage=_RNG.choice(PIPELINE_STAGES),
            ).returning(notice.c.id)
        ).one()
        ids.append(row.id)
    return ids


def _seed_notice_extras(conn, notice_ids: list[int], topic_ids: dict[str, int]) -> None:
    topic_id_list = list(topic_ids.values())
    for i, notice_id in enumerate(notice_ids):
        conn.execute(
            insert(notice_score).values(
                notice_id=notice_id,
                interest_topic_id=_RNG.choice(topic_id_list),
                l2_score=_RNG.randint(-2, 12),
                l3_conf=round(_RNG.uniform(0.4, 0.98), 3),
                priority=round(_RNG.uniform(0.1, 2.0), 3),
                reason="시드 데이터 — 실제 판정 아님",
                rule_ver=1,
            )
        )
        if i % 15 == 0:
            conn.execute(
                insert(notice_version).values(
                    notice_id=notice_id, ver=2, changed_fields={"close_dt": "연장됨"},
                )
            )
        if i % 10 == 0:
            conn.execute(
                insert(requirement).values(
                    notice_id=notice_id, type="실적", value="최근 3년 유사 실적 2건 이상", we_qualify=_RNG.choice([True, False, None]),
                )
            )
        if i % 8 == 0:
            action = _RNG.choice(["confirm", "recategorize", "irrelevant"])
            conn.execute(
                insert(classification_correction).values(
                    notice_id=notice_id,
                    action=action,
                    categories=[_RNG.choice(topic_id_list)] if action == "recategorize" else None,
                    reason="범위 밖" if action == "irrelevant" else None,
                )
            )


def _seed_awards(conn, notice_ids: list[int], org_ids: list[int]) -> None:
    for i in range(40):
        conn.execute(
            insert(award).values(
                notice_id=_RNG.choice(notice_ids),
                org_id=_RNG.choice(org_ids),
                winner_name=f"주식회사 시드업체{i % 7}",
                amount=_RNG.randint(3_000, 400_000) * 10_000,
                awarded_at=_now() - timedelta(days=_RNG.randint(1, 200)),
            )
        )


def _seed_customer_extras(conn, customer_ids: dict[str, int], org_ids: list[int]) -> None:
    conn.execute(insert(customer_interest_term).values(customer_id=customer_ids["(주)그립"], term="영상관제"))
    conn.execute(
        insert(customer_followed_org).values(customer_id=customer_ids["(주)그립"], org_id=_RNG.choice(org_ids))
    )


def _seed_products(conn, grib_customer_id: int) -> list[int]:
    products = [
        ("CLAIX AI Box", "영상분석 엣지장비"),
        ("CLAIX AI Board", "영상분석 보드"),
        ("CLAIX 관제 SW", "통합관제 소프트웨어"),
    ]
    ids = []
    for name, desc in products:
        row = conn.execute(
            insert(product).values(customer_id=grib_customer_id, name=name, category="영상분석", description=desc, active=True)
            .returning(product.c.id)
        ).one()
        ids.append(row.id)
        conn.execute(insert(product_spec).values(product_id=row.id, key="해상도", value="3840x2160", unit="px", op="gte"))
        conn.execute(insert(product_spec).values(product_id=row.id, key="프레임률", value="30", unit="fps", op="gte"))
        conn.execute(
            insert(product_cert).values(
                product_id=row.id, kind="GS인증", detail="1등급",
                issued_at=_now() - timedelta(days=200), expires_at=_now() + timedelta(days=60),
            )
        )
        conn.execute(
            insert(product_reference).values(
                product_id=row.id, org_name="한국수자원공사", project="댐 안전관제 고도화",
                amount=350_000_000, completed_at=_now() - timedelta(days=100), has_proof=True,
            )
        )
    return ids


def _seed_analyses(conn, notice_ids: list[int], product_ids: list[int]) -> None:
    cases = [
        {
            "verdict": "조건부 참여 권고", "confidence": 0.72, "status": "done",
            "req_judgement": "ok", "extract_ok": True,
        },
        {
            "verdict": "확인 필요 — 문서 추출 일부 실패", "confidence": 0.35, "status": "done",
            "req_judgement": "unknown", "extract_ok": False,
        },
    ]
    for i, case in enumerate(cases):
        row = conn.execute(
            insert(analysis).values(
                notice_id=notice_ids[i], source_kind="notice", input_ref=str(notice_ids[i]),
                status=case["status"], step="완료", started_at=_now() - timedelta(hours=1), finished_at=_now(),
                verdict=case["verdict"], confidence=case["confidence"], llm_tokens=4200, llm_cost=0.08,
                ver=1,
            ).returning(analysis.c.id)
        ).one()
        conn.execute(
            insert(analysis_doc).values(
                analysis_id=row.id, name=f"규격서_{i}.hwp", kind="hwp", bytes=204800,
                sha256="0" * 64, extract_method="hwp_parser" if case["extract_ok"] else "ocr",
                extract_ok=case["extract_ok"], error=None if case["extract_ok"] else "표 영역 인식 실패",
            )
        )
        conn.execute(
            insert(analysis_requirement).values(
                analysis_id=row.id, category="해상도", req_text="4K(3840x2160) 이상",
                req_value="3840x2160", req_unit="px", op="gte", cite="규격서 3.2조",
                matched_product_id=product_ids[0], judgement=case["req_judgement"],
            )
        )
        conn.execute(
            insert(analysis_flag).values(
                analysis_id=row.id, title="특정 모델 스펙 의심", quote="ONVIF Profile S/T 전체 지원",
                judgement="주의", action="사람 확인 필요",
            )
        )
        conn.execute(
            insert(analysis_check).values(
                analysis_id=row.id, title="사업자등록증 제출", detail="입찰 참가 자격 서류",
                critical=True, done=False,
            )
        )


def _seed_audit_log(conn, source_ids: list[int]) -> None:
    conn.execute(
        insert(audit_log).values(
            actor="report@grib.co.kr", action="source.create", target_type="source",
            target_id=str(source_ids[0]), detail={"note": "시드 데이터"},
        )
    )
