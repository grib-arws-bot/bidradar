"""seed_data.py가 쓰는 시드용 상수 데이터. 파일이 500줄을 넘어서 분리했다(CLAUDE.md 코드 규칙).
값 자체는 seed_data.py에 있던 것 그대로 — 로직(_seed_*, run_seed)은 seed_data.py에 남는다.
"""

from __future__ import annotations

# L2-b 대분류 20개 — 확정(2026-09-02, 의사결정_로그 21번). 순서가 곧 관리자 화면(TopicsPage)
# 번호 1~20(interest_topic.sort_order)이 된다.
INTEREST_TOPICS = [
    "산업안전/CCTV·영상보안", "스마트제조/팩토리", "로봇/자동화", "IoT/센서", "AI/데이터",
    "스마트교육/에듀테크", "에너지/신재생·ESS", "환경/탄소중립", "헬스케어/바이오·의료기기",
    "모빌리티/자율주행", "반도체/디스플레이", "스마트시티/인프라관제", "국방/보안",
    "콘텐츠/미디어/XR", "물류/스마트항만", "농수산/스마트팜", "통신/5G·6G", "우주/항공",
    "관광", "핀테크/금융보안",
]

# 2026-09-02 — IRIS 실데이터 14건이 전부 "매칭없음"으로 나온 원인 진단(관심주제 분류 대조표
# 참고) 결과, IRIS의 문제가 아니라 우리 쪽 규칙 공백이었음이 드러나 나머지 18개 주제를 채웠다.
# core는 그 단어 하나만으로도 대분류가 사실상 확정되는 고유 용어라 4점(단독으로 L2_PROMOTE_
# THRESHOLD=4 통과) — R&D 공고 제목은 "OOO기술개발사업 신규과제 공고"처럼 core 단어 하나에
# 일반 문구만 붙는 경우가 많아, core를 3점(기존 CCTV/스마트교육처럼 문맥어와 합산 필요)으로
# 두면 실제로 있던 실제 공고 다수가 승급 문턱을 못 넘었다(1차 실측으로 확인). tech/ctx/block
# 구성은 기존 2개 주제와 동일한 관례를 따름 — weight_class 자체는 채점에 안 쓰이고(app/
# collector/scorer.py) 사람이 규칙을 관리할 때 구분하기 위한 표시일 뿐이다.
#
# 보강 출처(2026-09-02, 사용자 제공 링크) — https://dinonino.tistory.com/161 "IT 산업 14개
# 분야" 목록에서 우리 20개 주제에 실제로 대응되는 세부 키워드만 tech로 보탰다(문서 자체가
# 취업/산업분석용이라 어휘 그대로 채택하지 않고 실제 공고 제목에 나올 법한 표현으로 다듬음).
# 네이버 블로그(m.blog.naver.com/bongkwankim/150149043291)는 옛 EUC-KR 인코딩이 손상돼 있어
# 정확한 어휘를 못 건졌지만, GICS·표준산업분류 기준 IT 산업을 "로봇·금융IT·물류IT·항공우주IT·
# 국방IT·문화IT·농업IT" 등으로 나누는 구조가 읽혀 — 우리 20개 주제 구조가 인정된 분류 관행과
# 크게 어긋나지 않는다는 걸 뒷받침하는 정도로만 참고(새 키워드는 여기서 가져오지 않았음).
KEYWORD_SEED = {
    "산업안전/CCTV·영상보안": [
        ("지능형 CCTV", "core", 3), ("영상관제", "core", 3), ("객체인식", "core", 3),
        ("IoT 센서", "tech", 2), ("무선 AP", "tech", 2), ("구축", "ctx", 1),
        ("임대", "block", -5), ("렌탈", "block", -5),
    ],
    "스마트제조/팩토리": [
        ("스마트공장", "core", 4), ("스마트팩토리", "core", 4),
        ("MES", "tech", 2), ("디지털트윈", "tech", 2), ("SCADA", "tech", 2),
        ("고도화", "ctx", 1), ("구축", "ctx", 1),
    ],
    "로봇/자동화": [
        ("로봇", "core", 4), ("협동로봇", "core", 4),
        ("자동화설비", "tech", 2), ("무인이동체", "tech", 2), ("드론", "tech", 2),
        ("구축", "ctx", 1), ("도입", "ctx", 1),
        ("임대", "block", -5), ("렌탈", "block", -5),
    ],
    "IoT/센서": [
        ("IoT", "core", 4), ("사물인터넷", "core", 4),
        ("센서", "tech", 2), ("무선 AP", "tech", 2),
        ("구축", "ctx", 1),
        ("임대", "block", -5), ("렌탈", "block", -5),
    ],
    "AI/데이터": [
        ("인공지능", "core", 4), ("AI", "core", 4), ("빅데이터", "core", 4),
        ("머신러닝", "tech", 2), ("딥러닝", "tech", 2), ("데이터플랫폼", "tech", 2), ("데이터분석", "tech", 2),
        ("구축", "ctx", 1), ("고도화", "ctx", 1),
    ],
    "에너지/신재생·ESS": [
        ("태양광", "core", 4), ("풍력", "core", 4), ("신재생에너지", "core", 4),
        ("ESS", "tech", 2), ("수소", "tech", 2),
        ("구축", "ctx", 1), ("설치", "ctx", 1),
    ],
    "환경/탄소중립": [
        ("탄소중립", "core", 4), ("온실가스", "core", 4),
        ("폐기물", "tech", 2), ("자원순환", "tech", 2), ("대기오염", "tech", 2), ("수질관리", "tech", 2),
        ("탄소배출", "tech", 2),
        ("관리", "ctx", 1),
    ],
    "헬스케어/바이오·의료기기": [
        ("의료기기", "core", 4), ("바이오", "core", 4), ("헬스케어", "core", 4),
        ("원격의료", "tech", 2), ("원격진료", "tech", 2), ("디지털헬스", "tech", 2), ("전자의무기록", "tech", 2),
        ("구매", "ctx", 1), ("구축", "ctx", 1),
    ],
    "모빌리티/자율주행": [
        ("자율주행", "core", 4), ("모빌리티", "core", 4),
        ("전기차", "tech", 2), ("충전인프라", "tech", 2), ("차량공유", "tech", 2),
        ("구축", "ctx", 1),
    ],
    "반도체/디스플레이": [
        ("반도체", "core", 4), ("디스플레이", "core", 4),
        ("웨이퍼", "tech", 2), ("OLED", "tech", 2),
        ("장비", "ctx", 1),
    ],
    "스마트시티/인프라관제": [
        ("스마트시티", "core", 4), ("통합관제센터", "core", 4),
        ("인프라관제", "tech", 2), ("시설물관리", "tech", 2),
        ("GIS", "tech", 2), ("공간정보", "tech", 2), ("위치기반서비스", "tech", 2), ("스마트빌딩", "tech", 2),
        ("구축", "ctx", 1),
    ],
    "국방/보안": [
        ("방위산업", "core", 4), ("사이버보안", "core", 4),
        ("정보보호", "tech", 2), ("국방", "tech", 2), ("보안솔루션", "tech", 2),
        ("구축", "ctx", 1),
    ],
    "콘텐츠/미디어/XR": [
        ("메타버스", "core", 4), ("가상현실", "core", 4), ("증강현실", "core", 4),
        ("XR", "tech", 2), ("콘텐츠", "tech", 2), ("VR", "tech", 2), ("AR", "tech", 2), ("스트리밍", "tech", 2),
        ("제작", "ctx", 1), ("구축", "ctx", 1),
    ],
    "물류/스마트항만": [
        ("스마트항만", "core", 4), ("물류센터", "core", 4),
        ("물류", "tech", 2), ("화물추적", "tech", 2), ("WMS", "tech", 2), ("재고관리", "tech", 2),
        ("구축", "ctx", 1),
    ],
    "농수산/스마트팜": [
        ("스마트팜", "core", 4), ("스마트농업", "core", 4),
        ("농업", "tech", 2), ("수산", "tech", 2), ("축산", "tech", 2),
        ("구축", "ctx", 1),
    ],
    "통신/5G·6G": [
        ("5G", "core", 4), ("6G", "core", 4),
        ("기지국", "tech", 2), ("통신망", "tech", 2),
        ("구축", "ctx", 1),
    ],
    "우주/항공": [
        ("위성", "core", 4), ("항공우주", "core", 4), ("우주항공", "core", 4),
        ("발사체", "tech", 2), ("드론", "tech", 2),
        ("구축", "ctx", 1),
    ],
    "관광": [
        ("관광", "core", 4),
        ("관광안내소", "tech", 2), ("관광상품", "tech", 2),
        ("조성", "ctx", 1), ("구축", "ctx", 1),
    ],
    "핀테크/금융보안": [
        ("핀테크", "core", 4), ("금융보안", "core", 4),
        ("전자결제", "tech", 2), ("블록체인", "tech", 2),
        ("간편결제", "tech", 2), ("모바일뱅킹", "tech", 2), ("로보어드바이저", "tech", 2),
        ("구축", "ctx", 1),
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

# 법적 등급(legal_tier)은 advisory INBOX #5(2026-09-01)에서 도입 — A(자유)/B(조건부)/C(금지).
# C등급 후보(NTIS·S2B·KIAT·SEMAS·NRF·KETEP·IPET·IITP)는 아직 실제로 등록된 소스가 없어(활성화
# 자체가 금지 대상이라 등록할 이유가 없음) SOURCE_SEED엔 A/B만 나온다 — app/collector/runner.py
# run_source가 C등급은 활성화 자체를 거부하므로, 나중에 실수로 추가돼도 수집은 안 된다.
SOURCE_SEED = [
    # (이름, 기관, base_url, 홈페이지, 단계, 어댑터, is_system, skip_l1, 수집주기(분),
    #  법적등급, 등급 근거, 근거 페이지)
    ("나라장터 발주계획현황서비스", "조달청", "https://apis.data.go.kr/1230000/OrderPlanSttusService",
     "https://www.data.go.kr/data/15129462/openapi.do", "발주계획", "openapi", True, True, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129462/openapi.do"),
    ("나라장터 사전규격정보서비스", "조달청", "https://apis.data.go.kr/1230000/ao/PubDataOpnStdService",
     "https://www.data.go.kr/data/15129437/openapi.do", "사전규격", "openapi", True, False, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129437/openapi.do"),
    ("나라장터 입찰공고정보서비스", "조달청", "https://apis.data.go.kr/1230000/BidPublicInfoService",
     "https://www.data.go.kr/data/15129394/openapi.do", "입찰공고", "openapi", True, False, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129394/openapi.do"),
    ("나라장터 낙찰정보서비스", "조달청", "https://apis.data.go.kr/1230000/ScsbidInfoService",
     "https://www.data.go.kr/data/15129397/openapi.do", "낙찰", "openapi", True, False, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129397/openapi.do"),
    ("K-water 입찰공고", "한국수자원공사", "https://apis.data.go.kr/B500001/kwaterBidInfo",
     "https://www.data.go.kr/data/15101635/openapi.do", "입찰공고", "openapi", False, False, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15101635/openapi.do"),
    # advisory INBOX #3(2026-09-01)로 교체 — "IRIS 사업공고"(범위 불명확한 자리표시자)를
    # "IRIS 접수예정"(접수중·마감은 이번 범위 아님, POST 폼 전송 필요해 별도 항목)으로 대체.
    # 어댑터도 html→openapi로 재분류 — 실제로 확인해보니 페이지 자체(GET)는 빈 템플릿이고,
    # 진짜 데이터는 별도 JSON 엔드포인트(POST)에서 나옴. HTML 파싱이 필요 없어 openapi 어댑터를
    # 그대로 재사용한다(2026-09-01 직접 검증 — advisory 원안의 "GET·서버렌더링" 설명과 다름,
    # 새 INBOX에도 같은 원안 설명이 반복되지만 직접 검증한 이 경로를 유지한다 — 의사결정_로그 #14).
    # stage="공모예고"(2026-09-01) — "사업공고"로 두면 이미 공식 공고된 단계(입찰공고 탭)와
    # 섞인다. 접수예정은 아직 공식 접수 전이라 사전규격·발주계획과 같은 묶음(공고탐색 탭 2번)에
    # 들어가야 의미가 맞는다. 법적등급 B(조건부) — INBOX #5: robots 허용·명시적 금지 없음이라
    # 수집 자체는 되지만, 원문 미저장(요약 필드만 매핑돼 있음)·출처링크 필수·최소 수집 간격을
    # 코드가 강제한다(app/collector/runner.py run_source).
    ("IRIS 접수예정", "과학기술정보통신부 등(범부처, 42개 전문기관)",
     "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do",
     "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do", "공모예고", "openapi", False, True, 1440,
     "B", "robots.txt 허용, 명시적 재배포 금지 문구 없음(2026-09-01 확인) — 원문 미저장·요약+링크만, 최소 수집 간격(1일) 강제",
     "https://www.iris.go.kr/robots.txt"),
    # 2026-09-02(의사결정_로그 24번) — IRIS 사업정보 메뉴 4개 화면 전수조사 중 발견. "접수예정"
    # (위 소스)보다도 이른 단계 — 접수예정/접수중/마감 탭과는 별개의 화면(retrieveAncmPrntc*)이라
    # 별도 소스로 등록. 목록 응답 자체에 사업내용·목적·지원분야 요약(35~230자, 원문 아님)과
    # 지원금액범위·지원기간까지 있어 상세페이지 없이도 정보가 풍부함(사업담당자 개인정보는
    # 상세페이지에만 있고 이 목록엔 없음, 3건 표본 확인). stage="공모예고" 재사용 — 둘 다
    # 공식 공고 전 단계라 같은 탭(사전규격/발주계획/공모예고)에 묶이는 게 맞음.
    ("IRIS 공모예고", "과학기술정보통신부 등(범부처, 42개 전문기관)",
     "https://www.iris.go.kr/contents/retrieveAncmPrntcList.do",
     "https://www.iris.go.kr/contents/retrieveAncmPrntcListView.do", "공모예고", "openapi", False, True, 1440,
     "B", "robots.txt 허용, 명시적 재배포 금지 문구 없음(IRIS 접수예정과 동일 사이트·동일 근거, 2026-09-02 확인) — 원문 미저장·요약+링크만, 최소 수집 간격(1일) 강제",
     "https://www.iris.go.kr/robots.txt"),
    # advisory INBOX #2(2026-09-01) — 과기정통부 "자체" 공고만 다룬다(범부처 아님). 이름에
    # 명시해 IRIS(범부처)와 혼동하지 않게 함. close_dt 항목 자체가 없는 소스 — INBOX #1 참고.
    # 법적등급 A(자유) — data.go.kr 이용허락범위 '제한 없음'.
    ("과학기술정보통신부 사업공고(부처 자체, 범부처 아님)", "과학기술정보통신부",
     "https://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList",
     "https://www.data.go.kr/data/15074634/openapi.do", "사업공고", "openapi", False, True, 1440,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15074634/openapi.do"),
    ("관리자 등록 예시 소스", "테스트기관", "https://example.grib-test.kr/notices",
     None, "입찰공고", "feed", False, True, 60,
     "A", "테스트용 자리표시자 — 실제 외부 소스 아님, 등급 판단 대상 아님", None),
]

# 출처표시 문구(advisory INBOX #7) — 소스명 → 뉴스레터/공유리포트 하단에 자동으로 붙일 문구.
# 공공데이터포털 정책상 제0유형 외 전 유형 출처표시 의무 — 사람이 매번 기억해서 붙이는 게
# 아니라 여기 한 곳에서 관리하고 템플릿이 자동으로 가져다 쓰게 한다. "관리자 등록 예시 소스"는
# 테스트용이라 뺀다(실제 리포트에 나올 일이 없음).
ATTRIBUTION_TEXT = {
    "나라장터 발주계획현황서비스": "출처: 조달청 나라장터 발주계획현황서비스(공공데이터포털)",
    "나라장터 사전규격정보서비스": "출처: 조달청 나라장터 사전규격정보서비스(공공데이터포털)",
    "나라장터 입찰공고정보서비스": "출처: 조달청 나라장터 입찰공고정보서비스(공공데이터포털)",
    "나라장터 낙찰정보서비스": "출처: 조달청 나라장터 낙찰정보서비스(공공데이터포털)",
    "K-water 입찰공고": "출처: 한국수자원공사 입찰공고(공공데이터포털)",
    "IRIS 접수예정": "출처: IRIS(범부처통합연구지원시스템) — 원문은 공고 링크에서 확인하세요",
    "IRIS 공모예고": "출처: IRIS(범부처통합연구지원시스템) — 원문은 공고 링크에서 확인하세요",
    "과학기술정보통신부 사업공고(부처 자체, 범부처 아님)": "출처: 과학기술정보통신부 사업공고(공공데이터포털)",
}

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
            # 업무구분(물품/용역/공사/외자)은 나라장터 응답 필드가 아니라 "어느 오퍼레이션을
            # 불렀는지"로 정해진다(2026-09-02 확인) — 이 엔드포인트(getBidPblancListInfoServc)는
            # 4종 중 "용역" 전용. 물품(getBidPblancListInfoThing)·공사(getBidPblancListInfoCnstwk)·
            # 외자(getBidPblancListInfoFrgcpt)는 별도 소스로 등록해야 함(아직 미등록).
            "biz_type": "용역",
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
            # 2026-09-02 — IRIS는 날짜범위 파라미터를 안 받는다(공고일 기준 요청 필터 자체가
            # 없음, techFildArr 등은 분야 필터일 뿐). 대신 pageIndex로만 넘어가고 응답의
            # paginationInfo.totalPageCount로 전체 페이지 수를 알 수 있어, 전 페이지를 받은 뒤
            # runner._collection_window()가 계산한 begin(2개월 캡)으로 클라이언트측에서 자른다.
            "pagination": {"page_param": "pageIndex", "total_path": "$.paginationInfo.totalPageCount", "max_pages": 20},
        },
        "field_maps": [
            ("notice_no", "$.ancmNo", None),
            ("title", "$.ancmTl", None),
            ("org_name", "$.sorgnNm", None),
            ("open_dt", "$.ancmDe", "%Y-%m-%d"),
            ("close_dt", "$.rcveEndDe", "%Y.%m.%d"),
            ("url", "urlfmt:https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId={ancmId}", None),
            # 2026-09-02 — 명명 컬럼에 안 들어가는 나머지 필드(공모유형·소관부처·접수상태·D-day
            # 등)를 notice.extra에 담아 화면 카드에 보여준다(전부 목록 응답에 이미 있던 값 —
            # 사업담당자·연락처 같은 개인정보는 상세페이지에만 있고 목록 응답엔 없음을 직접
            # 확인함, 그래도 mapper.validate_field_maps가 재차 걸러줌).
            ("extra:dDay", "$.dDay", None),
            ("extra:rcveStt", "$.rcveStt", None),
            ("extra:rcveSttSeNmLst", "$.rcveSttSeNmLst", None),
            ("extra:rcveStrDe", "$.rcveStrDe", None),
            ("extra:sorgnId", "$.sorgnId", None),
            ("extra:blngGovdSe", "$.blngGovdSe", None),
            ("extra:blngGovdSeNm", "$.blngGovdSeNm", None),
            ("extra:budJuriGovdSe", "$.budJuriGovdSe", None),
            ("extra:pbofrTpSeLst", "$.pbofrTpSeLst", None),
            ("extra:pbofrTpSeNmLst", "$.pbofrTpSeNmLst", None),
        ],
    },
    # 2026-09-02(의사결정_로그 24번) — 실제 POST 호출로 직접 확인(서비스키 불필요). 591건인데
    # **정렬 기준이 날짜순이 아니라 bsnsPrntcNo(등록순서) 내림차순**임을 라이브 검증으로 확인
    # (실측: 300건만 받았을 때 regDt가 2024-10-02~2026-08-28로 뒤섞여 있고 단조감소가 아니었음
    # — 최근 60일 이내 건이 뒤쪽 페이지에 더 있을 수 있어 max_pages를 전체(591/10≈60페이지)를
    # 커버하도록 65로 올림. B등급 최소 수집 간격(1일)상 하루 한 번이라 페이지 수가 늘어도 부담
    # 크지 않음). url은 상세페이지가 POST 폼 전용이라 advisory 원안처럼 GET querystring이 안
    # 먹힐 줄 알았으나, 실측 결과 같은 파라미터를 GET으로 보내도 200 정상 응답(직접 확인) —
    # urlfmt로 조립 가능. regMbrNm(등록회원명)은 응답에 있지만 실명이 아니라 회원코드값이라도
    # mapper의 PII 패턴("mbr")이 자동으로 막아준다 — 매핑 시도 자체를 안 함.
    "IRIS 공모예고": {
        "config": {
            "endpoint": "https://www.iris.go.kr/contents/retrieveAncmPrntcList.do",
            "method": "POST",
            "params": {"pageIndex": "1", "prgmId": ""},
            "items_path": "$.listAncmPrntc[*]",
            "pagination": {"page_param": "pageIndex", "total_path": "$.paginationInfo.totalPageCount", "max_pages": 65},
        },
        "field_maps": [
            ("notice_no", "$.bsnsPrntcNo", None),
            ("title", "$.ancmPrntcTl", None),
            ("org_name", "$.sorgnNm", None),
            ("open_dt", "$.regDt", "%Y-%m-%d"),
            (
                "url",
                "urlfmt:https://www.iris.go.kr/contents/retrieveAncmPrntcView.do?ancmId=&bsnsYy={bsnsYy}&sorgnBsnsCd={sorgnBsnsCd}&ancmPrntcSn=&ancmTurn=&seq={seq}&hirkSorgnBsnsCd={hirkSorgnBsnsCd}&sorgnId={sorgnId}",
                None,
            ),
            ("extra:blngGovdSeNm", "$.blngGovdSeNm", None),
            ("extra:bsnsYy", "$.bsnsYy", None),
            ("extra:bsnsCn", "$.bsnsCn", None),
            ("extra:bsnsPursCn", "$.bsnsPursCn", None),
            ("extra:sprtFildCn", "$.sprtFildCn", None),
            ("extra:sprtMinRsctAm", "$.sprtMinRsctAm", None),
            ("extra:sprtMxRsctAm", "$.sprtMxRsctAm", None),
            ("extra:sprtPridSe", "$.sprtPridSe", None),
            ("extra:bsnsSpchClSeNm", "$.bsnsSpchClSeNm", None),
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
