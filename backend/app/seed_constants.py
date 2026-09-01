"""seed_data.py가 쓰는 시드용 상수 데이터. 파일이 500줄을 넘어서 분리했다(CLAUDE.md 코드 규칙).
값 자체는 seed_data.py에 있던 것 그대로 — 로직(_seed_*, run_seed)은 seed_data.py에 남는다.
"""

from __future__ import annotations

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
    # (이름, 기관, base_url, 홈페이지, 단계, 어댑터, is_system, skip_l1, 수집주기(분))
    ("나라장터 발주계획현황서비스", "조달청", "https://apis.data.go.kr/1230000/OrderPlanSttusService",
     "https://www.data.go.kr/data/15129462/openapi.do", "발주계획", "openapi", True, True, 60),
    ("나라장터 사전규격정보서비스", "조달청", "https://apis.data.go.kr/1230000/ao/PubDataOpnStdService",
     "https://www.data.go.kr/data/15129437/openapi.do", "사전규격", "openapi", True, False, 60),
    ("나라장터 입찰공고정보서비스", "조달청", "https://apis.data.go.kr/1230000/BidPublicInfoService",
     "https://www.data.go.kr/data/15129394/openapi.do", "입찰공고", "openapi", True, False, 60),
    ("나라장터 낙찰정보서비스", "조달청", "https://apis.data.go.kr/1230000/ScsbidInfoService",
     "https://www.data.go.kr/data/15129397/openapi.do", "낙찰", "openapi", True, False, 60),
    ("K-water 입찰공고", "한국수자원공사", "https://apis.data.go.kr/B500001/kwaterBidInfo",
     "https://www.data.go.kr/data/15101635/openapi.do", "입찰공고", "openapi", False, False, 60),
    # advisory INBOX #3(2026-09-01)로 교체 — "IRIS 사업공고"(범위 불명확한 자리표시자)를
    # "IRIS 접수예정"(접수중·마감은 이번 범위 아님, POST 폼 전송 필요해 별도 항목)으로 대체.
    # 어댑터도 html→openapi로 재분류 — 실제로 확인해보니 페이지 자체(GET)는 빈 템플릿이고,
    # 진짜 데이터는 별도 JSON 엔드포인트(POST)에서 나옴. HTML 파싱이 필요 없어 openapi 어댑터를
    # 그대로 재사용한다(2026-09-01 직접 검증 — advisory 원안의 "GET·서버렌더링" 설명과 다름).
    # stage="공모예고"(2026-09-01) — "사업공고"로 두면 이미 공식 공고된 단계(입찰공고 탭)와
    # 섞인다. 접수예정은 아직 공식 접수 전이라 사전규격·발주계획과 같은 묶음(공고탐색 탭 2번)에
    # 들어가야 의미가 맞는다.
    ("IRIS 접수예정", "과학기술정보통신부 등(범부처, 42개 전문기관)",
     "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do",
     "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do", "공모예고", "openapi", False, True, 1440),
    # advisory INBOX #2(2026-09-01) — 과기정통부 "자체" 공고만 다룬다(범부처 아님). 이름에
    # 명시해 IRIS(범부처)와 혼동하지 않게 함. close_dt 항목 자체가 없는 소스 — INBOX #1 참고.
    ("과학기술정보통신부 사업공고(부처 자체, 범부처 아님)", "과학기술정보통신부",
     "https://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList",
     "https://www.data.go.kr/data/15074634/openapi.do", "사업공고", "openapi", False, True, 1440),
    ("관리자 등록 예시 소스", "테스트기관", "https://example.grib-test.kr/notices",
     None, "입찰공고", "feed", False, True, 60),
]

# U11 collector가 실제로 소비하는 정확한 config/필드매핑. 나머지 소스는 U13(등록마법사) 전까지
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
    },
    # advisory INBOX #2(2026-09-01) — 필드명(subject/viewUrl/pressDt 등)은 data.go.kr 문서
    # 기재값(advisory 조사 4절), 실호출로 검증된 건 아님(서비스키 발급 후 재확인 필요) ⚠️.
    # items_path는 나라장터 계열과 같은 관례(response.body.items)를 잠정 적용한 것 — 확정 아님.
    # close_dt 매핑이 없다 — 이 소스엔 마감일 항목 자체가 없음(INBOX #1, 의도적으로 비움).
    "과학기술정보통신부 사업공고(부처 자체, 범부처 아님)": {
        "config": {
            "endpoint": "https://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList",
            "params": {"type": "json", "numOfRows": "100", "pageNo": "1"},
            "items_path": "$.response.body.items[*]",
        },
        "field_maps": [
            ("title", "$.subject", None),
            ("org_name", "const:과학기술정보통신부", None),
            ("open_dt", "$.pressDt", "%Y%m%d"),
            ("url", "$.viewUrl", None),
        ],
    },
    # advisory INBOX #3(2026-09-01) — 필드명·엔드포인트는 실제 POST 호출로 직접 확인함(서비스키
    # 불필요, 공개 JSON 응답). advisory 원안은 "GET·html·서버렌더링"이었으나 검증 결과 정정 —
    # 실제로는 페이지 자체(GET)는 빈 템플릿만 오고, 진짜 데이터는 이 엔드포인트를 폼바디 POST로
    # 불러야 나온다(그래서 어댑터를 openapi로 재분류). 상세 URL은 응답에 없어 ancmId로 조립.
    # 접수중·마감 탭(POST 바디의 ancmPrg 값이 다름 — ancmIng/ancmEnd)은 이번 범위 아님(INBOX #3).
    "IRIS 접수예정": {
        "config": {
            "endpoint": "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do",
            "method": "POST",
            "params": {
                "pageIndex": "1", "prgmId": "", "pbofrTpArr": "", "ancmSttArr": "",
                "blngGovdSeArr": "", "sorgnIdArr": "", "qualCndtArr": "", "techFildArr": "",
            },
            "items_path": "$.listBsnsAncmBtinSitu[*]",
        },
        "field_maps": [
            ("notice_no", "$.ancmNo", None),
            ("title", "$.ancmTl", None),
            ("org_name", "$.sorgnNm", None),
            ("open_dt", "$.ancmDe", "%Y-%m-%d"),
            ("close_dt", "$.rcveEndDe", "%Y.%m.%d"),
            ("url", "urlfmt:https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId={ancmId}", None),
        ],
    },
}

# (제목 템플릿, 업무구분, 사업유형) — 사업유형은 app/collector/work_type.py의 실제 추정
# 규칙과 일치하게 맞춰뒀다(데모 데이터도 같은 근거로 채워지도록).
NOTICE_TITLE_TEMPLATES = [
    ("{org} 지능형 CCTV 통합관제시스템 구축", "용역", "구축"),
    ("{org} 스마트 안전관리시스템 고도화", "용역", "개발"),
    ("{org} IoT 센서 기반 시설물 안전관제 용역", "용역", "운영"),
    ("{org} AI 영상분석 관제 플랫폼 도입", "용역", "구축"),
    ("{org} 스마트교실 전자칠판 보급사업", "물품", "구매"),
    ("{org} AI 디지털교과서 단말 구매", "물품", "구매"),
    ("{org} 순찰로봇 시범사업", "용역", "구축"),
    ("{org} 무인이동체(드론) 안전점검 용역", "용역", "운영"),
    ("{org} 관제실 청소용역", "용역", "운영"),
    ("{org} CCTV 임대 및 유지보수", "용역", "유지보수"),
]

STAGES = ["발주계획", "사전규격", "공모예고", "입찰공고", "낙찰", "계약"]
PIPELINE_STAGES = ["collected", "l1_passed", "l2_scored", "l3_judged", "triaged", "archived"]
