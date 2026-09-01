"""python -m app.cli seed 가 호출하는 시드 데이터. 11절 — "빈 화면으로 개발하면 레이아웃이
틀어진다." 전 테이블(30개)에 최소 1행 이상 들어가야 U2 완료조건을 만족한다.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine, insert

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
    saved_search,
    source,
    source_config,
    source_credential,
    source_field_map,
    source_run,
)

_RNG = random.Random(42)  # 재현 가능한 시드

# L2-b 대분류 초안 20개 (설계안 05절 L2-b, 확정 아님 — 검토 대상)
INTEREST_TOPICS = [
    "산업안전/CCTV·영상보안", "스마트제조/팩토리", "로봇/자동화", "IoT/센서", "AI/데이터",
    "스마트교육/에듀테크", "에너지/신재생·ESS", "환경/탄소중립", "헬스케어/바이오·의료기기",
    "모빌리티/자율주행", "반도체/디스플레이", "스마트시티/인프라관제", "국방/보안",
    "콘텐츠/미디어/XR", "물류/스마트항만", "농수산/스마트팜", "통신/5G·6G", "우주/항공",
    "관광", "핀테크/금융보안",
]

KEYWORD_SEED = {
    "산업안전/CCTV·영상보안": [
        ("지능형 CCTV", "core", 3), ("영상관제", "core", 3), ("객체인식", "core", 3),
        ("IoT 센서", "tech", 2), ("무선 AP", "tech", 2), ("구축", "ctx", 1),
        ("임대", "block", -5), ("렌탈", "block", -5),
    ],
    "스마트교육/에듀테크": [
        ("스마트교실", "core", 3), ("전자칠판", "core", 3), ("AI 디지털교과서", "core", 3),
        ("무선 AP", "tech", 2), ("보급", "ctx", 1), ("급식", "block", -5),
    ],
}

# 발주기관 시드 — (기관명(한글), 기관약자(영어), 분류, 소속 SOURCE_SEED 이름 또는 None, 공고 URL 또는 None).
# "조달청"·"IRIS"는 발주기관이 아니라 공고기관(수집 채널)이라 여기 넣지 않는다(2026-09-01 지적) —
# 채널 자체는 source 테이블에서 관리하고, org.source_id로 어느 채널을 통해 수집되는지만 연결한다.
# 기관명은 가급적 한글로, 기관약자는 영어로 통일(2026-09-01 요청).
ORG_SEED = [
    ("한국수자원공사", None, "공기업(자체조달)", "K-water 입찰공고", "https://ebid.kwater.or.kr/"),
    ("한국도로공사", None, "공기업(자체조달)", None, "https://ebid.ex.co.kr/"),
    ("방위사업청", "DAPA", "중앙행정기관(자체조달)", None, "https://www.d2b.go.kr/"),
    ("한국토지주택공사", "LH", "공기업(자체조달)", None, "https://ebid.lh.or.kr/"),
    ("한국철도공사", "KORAIL", "공기업(자체조달)", None, "https://ebid.korail.com/"),
    ("국가철도공단", "KR", "공기업(자체조달)", None, "https://ebid.kr.or.kr/"),
    ("서울특별시교육청", None, "교육청", "나라장터 입찰공고정보서비스", None),
    ("부산광역시교육청", None, "교육청", "나라장터 입찰공고정보서비스", None),
    ("강원도교육청", None, "교육청", "나라장터 입찰공고정보서비스", None),
    ("정보통신산업진흥원", "NIPA", "R&D 지원기관", "나라장터 입찰공고정보서비스", None),
    ("한국콘텐츠진흥원", "KOCCA", "R&D 지원기관", None, None),
    ("한국에너지기술평가원", "KETEP", "R&D 지원기관", None, "https://www.ketep.re.kr/"),
    ("인천국제공항공사", "IIAC", "공기업(자체조달)", None, None),
]

SOURCE_SEED = [
    # (이름, 기관, base_url, 홈페이지, 단계, 어댑터, is_system, skip_l1)
    ("나라장터 발주계획현황서비스", "조달청", "https://apis.data.go.kr/1230000/OrderPlanSttusService",
     "https://www.data.go.kr/data/15129462/openapi.do", "발주계획", "openapi", True, True),
    ("나라장터 사전규격정보서비스", "조달청", "https://apis.data.go.kr/1230000/ao/PubDataOpnStdService",
     "https://www.data.go.kr/data/15129437/openapi.do", "사전규격", "openapi", True, False),
    ("나라장터 입찰공고정보서비스", "조달청", "https://apis.data.go.kr/1230000/BidPublicInfoService",
     "https://www.data.go.kr/data/15129394/openapi.do", "입찰공고", "openapi", True, False),
    ("나라장터 낙찰정보서비스", "조달청", "https://apis.data.go.kr/1230000/ScsbidInfoService",
     "https://www.data.go.kr/data/15129397/openapi.do", "낙찰", "openapi", True, False),
    ("K-water 입찰공고", "한국수자원공사", "https://apis.data.go.kr/B500001/kwaterBidInfo",
     "https://www.data.go.kr/data/15101635/openapi.do", "입찰공고", "openapi", False, False),
    ("IRIS 사업공고", "과학기술정보통신부 등", "https://www.iris.go.kr/contents/retrieveBsnsAncmListView.do",
     "https://www.iris.go.kr", "사업공고", "html", False, True),
    ("관리자 등록 예시 소스", "테스트기관", "https://example.grib-test.kr/notices",
     None, "입찰공고", "feed", False, True),
]

# U11 collector가 실제로 소비하는 정확한 config/필드매핑 — "나라장터 입찰공고정보서비스" 하나만
# 진짜 값으로 채워둔다(설계안 03절 호출 예시 그대로). 나머지 소스는 U13(등록마법사) 전까지
# 구조만 있으면 되는 자리표시자라 건드리지 않는다. DATA_GO_KR_SERVICE_KEY 환경변수가 실제로
# 설정되면 이 소스로 바로 `python -m app.cli collect --source-id <id>` 라이브 검증이 가능하다.
REAL_OPENAPI_CONFIG = {
    "나라장터 입찰공고정보서비스": {
        "config": {
            "endpoint": "https://apis.data.go.kr/1230000/BidPublicInfoService/getBidPblancListInfoServc",
            "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
            "date_range_params": {"begin": "inqryBgnDt", "end": "inqryEndDt", "format": "%Y%m%d%H%M"},
            "items_path": "$.response.body.items[*]",
        },
        "field_maps": [
            ("notice_no", "$.bidNtceNo", None),
            ("title", "$.bidNtceNm", None),
            ("org_name", "$.ntceInsttNm", None),
            ("open_dt", "$.bidNtceDt", "%Y%m%d%H%M"),
            ("close_dt", "$.bidClseDt", "%Y%m%d%H%M"),
            ("est_price", "$.presmptPrce", None),
            ("url", "$.bidNtceDtlUrl", None),
        ],
    }
}

NOTICE_TITLE_TEMPLATES = [
    "{org} 지능형 CCTV 통합관제시스템 구축", "{org} 스마트 안전관리시스템 고도화",
    "{org} IoT 센서 기반 시설물 안전관제 용역", "{org} AI 영상분석 관제 플랫폼 도입",
    "{org} 스마트교실 전자칠판 보급사업", "{org} AI 디지털교과서 단말 구매",
    "{org} 순찰로봇 시범사업", "{org} 무인이동체(드론) 안전점검 용역",
    "{org} 관제실 청소용역", "{org} CCTV 임대 및 유지보수",
]

STAGES = ["발주계획", "사전규격", "입찰공고", "낙찰", "계약"]
PIPELINE_STAGES = ["collected", "l1_passed", "l2_scored", "l3_judged", "triaged", "archived"]


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


def _seed_topics(conn) -> dict[str, int]:
    ids: dict[str, int] = {}
    for i, name in enumerate(INTEREST_TOPICS):
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
    rows = [
        {"name": "(주)그립", "plan_tier": "internal", "contact_email": "report@grib.co.kr"},
        {"name": "예시고객 A", "plan_tier": "standard", "contact_email": "customer-a@example.com"},
        {"name": "예시고객 B", "plan_tier": "standard", "contact_email": "customer-b@example.com"},
    ]
    ids: dict[str, int] = {}
    for row in rows:
        result = conn.execute(insert(customer).values(**row).returning(customer.c.id)).one()
        ids[row["name"]] = result.id

    # 그립·고객A는 관심주제 설정, 고객B는 비움(빈 상태 확인용 — 11절)
    for name in ("(주)그립", "예시고객 A"):
        for topic_name in ("산업안전/CCTV·영상보안", "스마트교육/에듀테크", "IoT/센서"):
            conn.execute(insert(customer_interest).values(customer_id=ids[name], interest_topic_id=topic_ids[topic_name]))
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


def _seed_sources(conn) -> tuple[list[int], list[int]]:
    source_ids: list[int] = []
    config_ids: list[int] = []
    for name, org_name, url, homepage_url, stage, adapter, is_system, skip_l1 in SOURCE_SEED:
        row = conn.execute(
            insert(source).values(
                name=name, org_name=org_name, base_url=url, homepage_url=homepage_url,
                stage=stage, adapter_type=adapter,
                frequency_minutes=60, is_system=is_system, skip_l1=skip_l1, active=True,
            ).returning(source.c.id)
        ).one()
        source_ids.append(row.id)

        real = REAL_OPENAPI_CONFIG.get(name)
        config = real["config"] if real else {"adapter": adapter, "endpoint": url}

        cfg_row = conn.execute(
            insert(source_config).values(
                source_id=row.id, ver=1, config=config, created_by="report@grib.co.kr",
            ).returning(source_config.c.id)
        ).one()
        config_ids.append(cfg_row.id)

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
        conn.execute(insert(source_credential).values(source_id=row.id, kind="service_key", value="__NOT_SET__"))

    return source_ids, config_ids


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
        title = _RNG.choice(NOTICE_TITLE_TEMPLATES).format(org=org_name_pick)
        open_dt = _now() - timedelta(days=_RNG.randint(0, 20))
        close_dt = _now() + timedelta(days=_RNG.randint(-1, 30))
        row = conn.execute(
            insert(notice).values(
                source_id=_RNG.choice(source_ids),
                source_ver=1,
                notice_no=f"SEED-{i:04d}",
                ord=0,
                stage=_RNG.choice(STAGES),
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
    for name in ("(주)그립", "예시고객 A"):
        conn.execute(insert(customer_interest_term).values(customer_id=customer_ids[name], term="영상관제"))
        conn.execute(insert(customer_followed_org).values(customer_id=customer_ids[name], org_id=_RNG.choice(org_ids)))
    conn.execute(
        insert(saved_search).values(
            customer_id=customer_ids["(주)그립"], name="이번 주 CCTV 공고",
            query_params={"q": "CCTV", "stage": "사전규격"},
        )
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
