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
        # 2026-09-05 추가 — 실제 수집 데이터 조사 결과 "안전관리 시스템"류 표현이 CCTV/영상관제
        # 키워드로는 전혀 안 걸려 산업안전 공고가 대량 누락되고 있었다(사용자 지적: "스마트 공원
        # 안전관리 시스템 유지보수 용역"이 왜 분류가 안 되냐). 공백 유무 두 형태 다 추가 —
        # score_l2가 단순 부분문자열 매칭이라 스페이싱이 다르면 안 걸린다.
        ("안전관리시스템", "tech", 2), ("안전관리 시스템", "tech", 2),
        ("지능형영상", "tech", 2), ("지능형 영상", "tech", 2), ("통합안전", "tech", 2),
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
        ("로보틱스", "tech", 2),  # 2026-09-05 추가 — "로봇"과 형태소가 달라 안 걸리던 실사례 발견
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
        ("CO2", "tech", 2),  # 2026-09-05 추가 — 실제 공고는 "탄소" 대신 영문 약자를 쓰는 경우가 있음
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
        ("위치기반서비스", "tech", 2), ("스마트빌딩", "tech", 2),
        # "GIS"·"공간정보"는 2026-09-05에 뺐다 — 실측 결과 이 주제 매칭 22건 중 21건이
        # "GIS"만으로 걸린 것이었고, 거의 전부 하수관로·노후관 개량 등 완전히 무관한 토목
        # 측량 용역이었다(진짜 관심공고 하나가 상위 20위 밖으로 밀려나는 원인이 됨, 사용자 지적).
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
        ("에듀테크", "core", 4),  # 2026-09-05 추가 — 주제명 자체인 핵심어가 정작 목록에 없었음
        ("원격수업", "tech", 2), ("디지털교과서", "tech", 2),
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
    ("한국가스공사", "KOGAS", "공기업(자체조달)", None, "https://bid.kogas.or.kr:9443/"),
    ("서울특별시교육청", None, "교육청", "나라장터 입찰공고정보서비스(용역)", None),
    ("부산광역시교육청", None, "교육청", "나라장터 입찰공고정보서비스(용역)", None),
    ("강원도교육청", None, "교육청", "나라장터 입찰공고정보서비스(용역)", None),
    ("정보통신산업진흥원", "NIPA", "R&D 지원기관", "나라장터 입찰공고정보서비스(용역)", None),
    ("한국콘텐츠진흥원", "KOCCA", "R&D 지원기관", None, None),
    ("한국에너지기술평가원", "KETEP", "R&D 지원기관", None, "https://www.ketep.re.kr/"),
    ("인천국제공항공사", "IIAC", "공기업(자체조달)", None, None),
]

# S8 파일럿 자동 실행(2026-09-05, 사용자 지시) — "IRIS는 수집과 동시에 첨부문서까지 자동
# 분석, 나라장터는 물량이 많으니 사용자가 선택할 때만"이라는 요청을 소스별 관리자 설정
# (source.auto_extract)으로 구현한다. 여기 있는 이름만 시드 시점에 True로 켠다 — 나머지는
# 전부 기본값 False(관리자가 "데이터 소스" 화면에서 언제든 개별로 켤 수 있음).
AUTO_EXTRACT_SOURCES = frozenset({"IRIS 접수예정", "IRIS 접수중"})  # IRIS 공모예고 제외(2026-09-05, 의사결정_로그 49번)

# 법적 등급(legal_tier)은 advisory INBOX #5(2026-09-01)에서 도입 — A(자유)/B(조건부)/C(금지).
# C등급 후보(NTIS·S2B·KIAT·SEMAS·NRF·KETEP·IPET·IITP)는 아직 실제로 등록된 소스가 없어(활성화
# 자체가 금지 대상이라 등록할 이유가 없음) SOURCE_SEED엔 A/B만 나온다 — app/collector/runner.py
# run_source가 C등급은 활성화 자체를 거부하므로, 나중에 실수로 추가돼도 수집은 안 된다.
SOURCE_SEED = [
    # (이름, 기관, base_url, 홈페이지, 단계, 어댑터, is_system, skip_l1, 수집주기(분),
    #  법적등급, 등급 근거, 근거 페이지)
    # 2026-09-03 — homepage_url을 data.go.kr API 문서 페이지에서 나라장터 실사이트(g2b.go.kr)로
    # 정정. "데이터 소스" 화면의 공고기관 링크가 data.go.kr로 가면 안 된다는 지적(사용자) —
    # data.go.kr 근거 링크는 license_evidence_url(준법 확인용, 사용자 화면에 안 나옴)에만 남긴다.
    # 2026-09-04 — 물품/용역/공사 3종으로 확장(REAL_OPENAPI_CONFIG 쪽 주석 참고). license_note는
    # 3종 동일(같은 API 데이터셋, 오퍼레이션만 다름).
    ("나라장터 발주계획현황서비스(용역)", "조달청", "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService/getOrderPlanSttusListServc",
     "https://www.g2b.go.kr/", "발주계획", "openapi", True, True, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129462/openapi.do"),
    ("나라장터 발주계획현황서비스(물품)", "조달청", "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService/getOrderPlanSttusListThng",
     "https://www.g2b.go.kr/", "발주계획", "openapi", True, True, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129462/openapi.do"),
    ("나라장터 발주계획현황서비스(공사)", "조달청", "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService/getOrderPlanSttusListCnstwk",
     "https://www.g2b.go.kr/", "발주계획", "openapi", True, True, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129462/openapi.do"),
    # 2026-09-05 — 등록 보류를 해제(사용자 지시). notice.url은 2026-09-10까지 첨부파일 다운로드
    # URL(specDocFileUrl1)로 대신 쓰다가, 사용자가 실제 상세페이지 URL 패턴(g2b.go.kr/link/
    # PRVA004_02/?bfSpecRegNo=사전규격등록번호, 로그인 불필요)을 브라우저에서 직접 확인해줘서
    # urlfmt: 템플릿으로 진짜 상세페이지 링크를 조립하도록 바뀌었다(아래 field_maps, 의사결정_로그
    # 참고). bfSpecRgstNo 자체가 없는 항목(첨부 유무와 무관, 극히 드묾)만 url이 빈 문자열이 돼
    # mapper의 필수필드 검사(REQUIRED_FIELDS)에 걸려 자동으로 건너뛰어진다.
    ("나라장터 사전규격정보서비스(용역)", "조달청", "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc",
     "https://www.g2b.go.kr/", "사전규격", "openapi", True, False, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129437/openapi.do"),
    ("나라장터 사전규격정보서비스(물품)", "조달청", "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoThng",
     "https://www.g2b.go.kr/", "사전규격", "openapi", True, False, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129437/openapi.do"),
    ("나라장터 사전규격정보서비스(공사)", "조달청", "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoCnstwk",
     "https://www.g2b.go.kr/", "사전규격", "openapi", True, False, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129437/openapi.do"),
    ("나라장터 입찰공고정보서비스(용역)", "조달청", "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc",
     "https://www.g2b.go.kr/", "입찰공고", "openapi", True, False, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129394/openapi.do"),
    # 2026-09-04 물품·공사를 active=False로 비활성화(L1 필터 부재로 무관한 전국 공고 혼입,
    # 37번 항목) → **2026-09-05 활성화로 변경됨(사용자 지시)**. L1 관련성 필터 자체는 아직
    # 스텁이라 여전히 무관한 공고가 섞여 들어오지만, 이미 마감된 공고를 걸러내는 장치(37번
    # 항목, runner.py already_closed)가 생겨 최소한 "82% 마감건 혼입" 문제는 재발하지 않는다.
    ("나라장터 입찰공고정보서비스(물품)", "조달청", "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoThng",
     "https://www.g2b.go.kr/", "입찰공고", "openapi", True, False, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129394/openapi.do"),
    ("나라장터 입찰공고정보서비스(공사)", "조달청", "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoCnstwk",
     "https://www.g2b.go.kr/", "입찰공고", "openapi", True, False, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129394/openapi.do"),
    # 2026-09-05 — 지금 단계에선 필요 없음(사용자 지시). Phase 2(분석 기능, 낙찰가·경쟁률 등
    # 시장 분석에 씀)까지 등록만 해두고 REAL_OPENAPI_CONFIG는 만들지 않는다 — 자리표시자
    # config라 실제로 collect를 돌려도 의미 있는 데이터가 안 나온다(안전).
    ("나라장터 낙찰정보서비스", "조달청", "https://apis.data.go.kr/1230000/ScsbidInfoService",
     "https://www.g2b.go.kr/", "낙찰", "openapi", True, False, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15129397/openapi.do"),
    # 2026-09-03 발견: xlsx가 준 "apis.data.go.kr/B500001/..." 주소는 처음부터 완전히 틀린
    # 호스트였다(26번 항목에서 "서비스 폐기"로 오판했던 원인) — data.go.kr 상세페이지에 숨어있는
    # Swagger 스펙(JSON)을 직접 찾아 확인한 결과 실제로는 한국수자원공사 자체 서버
    # (opendata.kwater.or.kr)에서 서비스된다.
    ("K-water 입찰공고", "한국수자원공사", "http://opendata.kwater.or.kr/openapi-data/service/pubd/ebid/tndr/dmscpt/list",
     "https://ebid.kwater.or.kr/", "입찰공고", "openapi", False, False, 60,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15101635/openapi.do"),
    # advisory INBOX #3(2026-09-01)로 교체 — "IRIS 사업공고"(범위 불명확한 자리표시자)를
    # "IRIS 접수예정"(접수중·마감은 이번 범위 아님, POST 폼 전송 필요해 별도 항목)으로 대체.
    # 어댑터도 html→openapi로 재분류 — 실제로 확인해보니 페이지 자체(GET)는 빈 템플릿이고,
    # 진짜 데이터는 별도 JSON 엔드포인트(POST)에서 나옴. HTML 파싱이 필요 없어 openapi 어댑터를
    # 그대로 재사용한다(2026-09-01 직접 검증 — advisory 원안의 "GET·서버렌더링" 설명과 다름,
    # 새 INBOX에도 같은 원안 설명이 반복되지만 직접 검증한 이 경로를 유지한다 — 의사결정_로그 #14).
    # stage="접수예정"(2026-09-05 수정, 의사결정_로그 52번 — 원래 "공모예고"였다가 소스명과
    # stage 값이 달라 사용자가 목록에서 혼동, 지금은 삭제한 "IRIS 공모예고" 소스와도 이름이
    # 겹쳐 잔존 데이터로 오인. 정부지원 생명주기(접수예정→접수중→접수마감, notice_classification.py)
    # 라벨과 그대로 맞춰 소스명=stage=생명주기 단계가 한눈에 일치하도록 통일). 법적등급 B(조건부)
    # — INBOX #5: robots 허용·명시적 금지 없음이라 수집 자체는 되지만, 원문 미저장(요약 필드만
    # 매핑돼 있음)·출처링크 필수·최소 수집 간격을 코드가 강제한다(app/collector/runner.py run_source).
    # org_name="IRIS"(2026-09-03) — "과학기술정보통신부 등(범부처, 42개 전문기관)"이라는 설명문을
    # 그대로 넣었더니 관리자 "데이터 소스" 화면의 채널 열에 그 긴 문장이 그대로 노출됐다. 이
    # 소스가 대표하는 기관 목록에 대한 설명은 안내 텍스트지 채널 이름이 아니다 — 실제 채널
    # 이름(IRIS)을 넣는다.
    ("IRIS 접수예정", "IRIS",
     "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do",
     "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do", "접수예정", "openapi", False, True, 1440,
     "B", "robots.txt 허용, 명시적 재배포 금지 문구 없음(2026-09-01 확인) — 원문 미저장·요약+링크만, 최소 수집 간격(1일) 강제",
     "https://www.iris.go.kr/robots.txt"),
    # 2026-09-05 — "접수중"(ancmPrg=ancmIng) 탭도 별도 소스로 등록(사용자 지시). 접수예정과
    # 동일 엔드포인트·필드매핑, ancmPrg 값과 stage만 다르다. 이미 공식으로 접수를 받고 있는
    # 단계라 stage="입찰공고"(나라장터의 "이미 열려서 접수 중" 의미와 동일선상). 같은 ancmId로
    # 이미 "IRIS 접수예정"에 저장된 공고를 다시 만나면 notice.url이 같아 새 행을 만들지 않고
    # 기존 행을 그대로 재사용한다(runner.py 기존 dedup 로직) — stage는 최초 수집 시점 값 그대로
    # 남지만 실시간 상태는 bid_status(open_dt/close_dt 기반 계산값, 33번 항목)가 대신한다.
    ("IRIS 접수중", "IRIS",
     "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do",
     "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do", "입찰공고", "openapi", False, True, 1440,
     "B", "robots.txt 허용, 명시적 재배포 금지 문구 없음(IRIS 접수예정과 동일 사이트·동일 근거)",
     "https://www.iris.go.kr/robots.txt"),
    # 2026-09-02(의사결정_로그 24번) — IRIS 사업정보 메뉴 4개 화면 전수조사 중 발견. "접수예정"
    # (위 소스)보다도 이른 단계 — 접수예정/접수중/마감 탭과는 별개의 화면(retrieveAncmPrntc*)이라
    # 별도 소스로 등록. 목록 응답 자체에 사업내용·목적·지원분야 요약(35~230자, 원문 아님)과
    # 지원금액범위·지원기간까지 있어 상세페이지 없이도 정보가 풍부함(사업담당자 개인정보는
    # 상세페이지에만 있고 이 목록엔 없음, 3건 표본 확인). stage="공모예고" 재사용 — 둘 다
    # 공식 공고 전 단계라 같은 탭(사전규격/발주계획/공모예고)에 묶이는 게 맞음.
    # homepage_url을 IRIS 접수예정과 동일하게 통일(2026-09-03, 사용자 지시) — 관리자 화면의
    # 채널명이 둘 다 "IRIS"로 통일됐으니(위 주석 참고) 링크도 하나의 대표 진입점으로 통일한다.
    ("IRIS 공모예고", "IRIS",
     "https://www.iris.go.kr/contents/retrieveAncmPrntcList.do",
     "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do", "공모예고", "openapi", False, True, 1440,
     "B", "robots.txt 허용, 명시적 재배포 금지 문구 없음(IRIS 접수예정과 동일 사이트·동일 근거, 2026-09-02 확인) — 원문 미저장·요약+링크만, 최소 수집 간격(1일) 강제",
     "https://www.iris.go.kr/robots.txt"),
    # advisory INBOX #2(2026-09-01) — 과기정통부 "자체" 공고만 다룬다(범부처 아님). 이름에
    # 명시해 IRIS(범부처)와 혼동하지 않게 함. close_dt 항목 자체가 없는 소스 — INBOX #1 참고.
    # 법적등급 A(자유) — data.go.kr 이용허락범위 '제한 없음'.
    ("과학기술정보통신부 사업공고(부처 자체, 범부처 아님)", "과학기술정보통신부",
     "https://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList",
     "https://www.msit.go.kr/bbs/list.do?sCode=user&mId=311&mPid=121", "사업공고", "openapi", False, True, 1440,
     "A", "공공데이터포털 이용허락범위 '제한 없음'(공공데이터법 제3조④) — 원문 재가공·유료 재배포 가능",
     "https://www.data.go.kr/data/15074634/openapi.do"),
    # 2026-09-13 — 나라장터·IRIS 외 신규 소스 조사(자체조달 갭분석)에서 추가. 국가철도공단은
    # data.go.kr에 전용 API가 없어 첫 html 어댑터로 도입(app/collector/adapters/html.py).
    # KR전자조달시스템(ebid.kr.or.kr) robots.txt 전면허용(Allow: /), 이용약관(/html/clause.html,
    # KR전자조달시스템입찰자이용약관)은 전자입찰 참가자 대상 조항뿐 — 크롤링·재배포 금지 조항
    # 없음(2026-09-13 직접 확인). 다만 공공데이터포털의 명시적 '제한없음' 라이선스 같은 적극적
    # 허가는 없는 상태라 IRIS와 동일한 근거로 법적등급 B(조건부) — 원문 전문은 안 쌓는다(목록에
    # 나오는 구조화 필드만 매핑, 첨부파일 다운로드는 이번 범위 밖).
    ("국가철도공단 입찰공고", "국가철도공단", "https://ebid.kr.or.kr/bid/anc/bidAncList.do",
     "https://ebid.kr.or.kr/", "입찰공고", "html", False, False, 60,
     "B", "robots.txt 전면허용, 이용약관에 크롤링·재배포 금지 조항 없음(전자입찰 참가자 대상 조항뿐, 2026-09-13 확인)",
     "https://ebid.kr.or.kr/robots.txt"),
    # 2026-09-14 — 자체조달 갭분석(2026-09-01) 후속으로 추가. 실측(Playwright로 실제 렌더링
    # 확인, WebFetch만으로는 정적 HTML이 비어 보여 "로그인 기반 SPA"로 오판할 뻔함) 결과 목록
    # 페이지(/supplier/contents/bid/bid_list_notice_frm.jsp)는 로그인 없이 GET으로 그대로
    # 열리는 전통적 JSP 게시판 — 국가철도공단과 같은 구조. robots.txt는 QnA 게시판 한 경로만
    # 차단(그 외 전면 허용), 이 서브도메인·회사 개인정보처리방침 어디에도 크롤링·재배포를 금지
    # 하는 이용약관 문구를 찾지 못함(2026-09-14 직접 확인) — 국가철도공단과 동일 근거로 법적
    # 등급 B. 비표준 포트 9443 필수(url_guard.ALLOWED_PORTS에 추가). 날짜범위 필터 파라미터
    # (e_startday 등)의 실제 동작을 검증 못해 사용하지 않고, 대신 max_pages를 작게 잡아(5페이지,
    # 최근 순 정렬 확인됨) 매 회차 최근 공고만 훑는다 — 전체 597건(40페이지)을 매번 다시
    # 긁는 낭비를 피함(29번 항목 OpenAPI 쿼터 사고에서 배운 "불필요한 반복 호출 최소화" 원칙).
    ("한국가스공사 입찰공고", "한국가스공사", "https://bid.kogas.or.kr:9443/supplier/contents/bid/bid_list_notice_frm.jsp",
     "https://bid.kogas.or.kr:9443/", "입찰공고", "html", False, False, 60,
     "B", "robots.txt 전면허용(QnA 게시판 1곳만 예외), 이용약관 문구 자체를 찾지 못함 — 명시적 금지 없음(2026-09-14 확인)",
     "https://bid.kogas.or.kr:9443/robots.txt"),
]
# "관리자 등록 예시 소스"(테스트용 자리표시자) 2026-09-05 삭제(사용자 지시) — 실 소스만 남긴다.

# 출처표시 문구(advisory INBOX #7) — 소스명 → 뉴스레터/공유리포트 하단에 자동으로 붙일 문구.
# 공공데이터포털 정책상 제0유형 외 전 유형 출처표시 의무 — 사람이 매번 기억해서 붙이는 게
# 아니라 여기 한 곳에서 관리하고 템플릿이 자동으로 가져다 쓰게 한다.
ATTRIBUTION_TEXT = {
    "나라장터 발주계획현황서비스(용역)": "출처: 조달청 나라장터 발주계획현황서비스(공공데이터포털)",
    "나라장터 발주계획현황서비스(물품)": "출처: 조달청 나라장터 발주계획현황서비스(공공데이터포털)",
    "나라장터 발주계획현황서비스(공사)": "출처: 조달청 나라장터 발주계획현황서비스(공공데이터포털)",
    "나라장터 사전규격정보서비스(용역)": "출처: 조달청 나라장터 사전규격정보서비스(공공데이터포털)",
    "나라장터 사전규격정보서비스(물품)": "출처: 조달청 나라장터 사전규격정보서비스(공공데이터포털)",
    "나라장터 사전규격정보서비스(공사)": "출처: 조달청 나라장터 사전규격정보서비스(공공데이터포털)",
    "나라장터 입찰공고정보서비스(용역)": "출처: 조달청 나라장터 입찰공고정보서비스(공공데이터포털)",
    "나라장터 입찰공고정보서비스(물품)": "출처: 조달청 나라장터 입찰공고정보서비스(공공데이터포털)",
    "나라장터 입찰공고정보서비스(공사)": "출처: 조달청 나라장터 입찰공고정보서비스(공공데이터포털)",
    "나라장터 낙찰정보서비스": "출처: 조달청 나라장터 낙찰정보서비스(공공데이터포털)",
    "K-water 입찰공고": "출처: 한국수자원공사 입찰공고(공공데이터포털)",
    "IRIS 접수예정": "출처: IRIS(범부처통합연구지원시스템) — 원문은 공고 링크에서 확인하세요",
    "IRIS 접수중": "출처: IRIS(범부처통합연구지원시스템) — 원문은 공고 링크에서 확인하세요",
    "IRIS 공모예고": "출처: IRIS(범부처통합연구지원시스템) — 원문은 공고 링크에서 확인하세요",
    "과학기술정보통신부 사업공고(부처 자체, 범부처 아님)": "출처: 과학기술정보통신부 사업공고(공공데이터포털)",
    "국가철도공단 입찰공고": "출처: 국가철도공단 KR전자조달시스템 — 원문은 공고 링크에서 확인하세요",
    "한국가스공사 입찰공고": "출처: 한국가스공사 전자조달시스템 — 원문은 공고 링크에서 확인하세요",
}

# U11 collector가 실제로 소비하는 정확한 config/필드매핑. 나머지 소스는 U13(등록마법사) 전까지
# 구조만 있으면 되는 자리표시자라 건드리지 않는다. DATA_GO_KR_SERVICE_KEY 환경변수가 실제로
# 설정되면 이 소스로 바로 `python -m app.cli collect --source-id <id>` 라이브 검증이 가능하다.
REAL_OPENAPI_CONFIG = {
    # 2026-09-04 — 물품·용역·공사 3종으로 확장(사용자 지시: "3개 서비스만으로 전체 기능").
    # 3종 모두 필드명이 동일해 아래 field_maps를 그대로 재사용, 오퍼레이션 경로와 biz_type만
    # 다르다(2026-09-04 라이브 3종 실측으로 필드 동일성 확인). 첨부문서(ntceSpecDocUrl1~10 +
    # ntceSpecFileNm1~10, 최대 10개)는 API 응답에 다운로드 URL이 이미 직접 들어있어 IRIS처럼
    # HTML에서 발견할 필요가 없다 — 단 이번 등록 범위는 목록·상세 필드까지만이고, 이 첨부파일들을
    # S8 추출 파이프라인에 연결하는 건 별도 작업으로 남긴다(analysis_pilot.py는 아직 IRIS 전용).
    #
    # ⚠️ 날짜 포맷 버그 발견(2026-09-04) — 기존 "용역" 항목의 format_hint가 "%Y%m%d%H%M"였는데
    # 실제 응답은 "2026-09-01 03:00:32"(대시·콜론 포함) 형식이라 매번 파싱 실패 → open_dt가
    # 필수 필드(mapper.REQUIRED_FIELDS)라 모든 항목이 조용히 skipped 처리되고 있었다(실제 DB에
    # 나라장터 공고 0건으로 확인). 서비스키 승인이 이번에 처음 나서 지금까지 한 번도 실행된 적이
    # 없어 발견이 늦었다 — 3종 모두 올바른 포맷으로 수정.
    "나라장터 입찰공고정보서비스(용역)": {
        "config": {
            # 2026-09-03 발견: 원안(advisory INBOX)엔 "/ad/" 세그먼트가 빠져 있었다 — 그 상태로
            # 호출하면 NO_OPENAPI_SERVICE_ERROR("서비스가 없거나 폐기됨")가 나서 한동안 이 API
            # 자체가 폐기된 줄 알았는데, 조달청 공식 참고문서(advisory/공공데이타/조달청_OpenAPI
            # 참고자료_나라장터_입찰공고정보서비스_1.2.docx, "서비스 URL" 절)의 정확한 경로를
            # 넣으니 에러가 SERVICE_KEY_IS_NOT_REGISTERED_ERROR로 바뀜 — 즉 API 자체는 살아있고,
            # 이 서비스키가 이 데이터셋에 아직 승인이 안 된 것뿐이었다.
            "endpoint": "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc",
            "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
            "date_range_params": {"begin": "inqryBgnDt", "end": "inqryEndDt", "format": "%Y%m%d%H%M"},
            "items_path": "$.response.body.items[*]",
            "biz_type": "용역",
            # 2026-09-04 실측 — inqryBgnDt~inqryEndDt 구간이 60일이면 "입력범위값 초과 에러"
            # (resultCode 07), 30일은 정상. 페이지당 100건 고정이라 pagination 없이는 1페이지만
            # 가져와 나머지를 놓친다(용역 30일치가 100건을 훌쩍 넘음, 실측으로 확인).
            # 2026-09-05 — 30일치가 실제로 12,292건(직접 API 호출로 실측)이라 첫 백필이 아주
            # 오래 걸림(50페이지 상한까지 순회) — 7일로 낮춤(사용자 지시). 정기 수집은 어차피
            # 직전 성공 시각 기준으로 자동 좁혀지므로(_collection_window) 이 값은 "이력이 없거나
            # 공백이 클 때"만 적용되는 상한이다.
            # 2026-09-14 — total_path 추가(직접 호출로 response.body.totalCount 존재 확인,
            # numOfRows/pageNo와 형제 필드). 지금까지는 "빈 페이지에서 멈추는 방식"에 기대,
            # 매 회차 마지막에 빈 결과를 확인하는 호출을 한 번 더 썼다 — 이 서비스가 이 API
            # 제품군 안에서 일일 요청한도 초과(LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR)를
            # 반복해서 맞은 사고(2026-09-13) 조사 중 발견 — 불필요한 호출을 조금이라도 줄인다.
            "max_lookback_days": 7,
            "pagination": {"page_param": "pageNo", "total_path": "$.response.body.totalCount", "max_pages": 50},
        },
        "field_maps": [
            ("notice_no", "$.bidNtceNo", None),
            ("title", "$.bidNtceNm", None),
            ("org_name", "$.ntceInsttNm", None),
            # 2026-09-05 — open_dt를 bidNtceDt(공고 게시일)에서 bidBeginDt(입찰 개시일)로
            # 교체(사용자 발견) — 실측 5,000건 중 4,751건이 개시일이 게시일보다 늦음. 게시일은
            # 항상 "지금 아니면 과거"라 open_dt로 쓰면 "입찰예정" 상태가 구조적으로 절대 안
            # 나온다. 원래 게시일은 extra:bidNtceDt로 남긴다.
            ("open_dt", "$.bidBeginDt", "%Y-%m-%d %H:%M:%S"),
            ("close_dt", "$.bidClseDt", "%Y-%m-%d %H:%M:%S"),
            ("est_price", "$.presmptPrce", None),
            ("url", "$.bidNtceDtlUrl", None),
            ("extra:bidNtceDt", "$.bidNtceDt", None),  # 공고 게시일(참고용)
            ("extra:cntrctCnclsMthdNm", "$.cntrctCnclsMthdNm", None),  # 계약체결방법
            ("extra:opengDt", "$.opengDt", None),  # 개찰일시
        ],
    },
    "나라장터 입찰공고정보서비스(물품)": {
        "config": {
            "endpoint": "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoThng",
            "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
            "date_range_params": {"begin": "inqryBgnDt", "end": "inqryEndDt", "format": "%Y%m%d%H%M"},
            "items_path": "$.response.body.items[*]",
            "biz_type": "물품",
            "max_lookback_days": 30,
            # 2026-09-14 — total_path 추가(response.body.totalCount 실측 확인) — 불필요한
            # 트레일링 호출을 줄여 일일 요청한도 소모를 낮춘다(2026-09-13 초과 사고 조사 결과).
            "pagination": {"page_param": "pageNo", "total_path": "$.response.body.totalCount", "max_pages": 50},
        },
        "field_maps": [
            ("notice_no", "$.bidNtceNo", None),
            ("title", "$.bidNtceNm", None),
            ("org_name", "$.ntceInsttNm", None),
            ("open_dt", "$.bidBeginDt", "%Y-%m-%d %H:%M:%S"),  # 2026-09-05, 용역과 동일 이유
            ("close_dt", "$.bidClseDt", "%Y-%m-%d %H:%M:%S"),
            ("est_price", "$.presmptPrce", None),
            ("url", "$.bidNtceDtlUrl", None),
            ("extra:bidNtceDt", "$.bidNtceDt", None),
            ("extra:cntrctCnclsMthdNm", "$.cntrctCnclsMthdNm", None),
            ("extra:opengDt", "$.opengDt", None),
            ("extra:dtilPrdctClsfcNoNm", "$.dtilPrdctClsfcNoNm", None),  # 세부품명(물품 전용)
        ],
    },
    "나라장터 입찰공고정보서비스(공사)": {
        "config": {
            "endpoint": "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoCnstwk",
            "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
            "date_range_params": {"begin": "inqryBgnDt", "end": "inqryEndDt", "format": "%Y%m%d%H%M"},
            "items_path": "$.response.body.items[*]",
            "biz_type": "공사",
            "max_lookback_days": 30,
            # 2026-09-14 — total_path 추가(response.body.totalCount 실측 확인) — 불필요한
            # 트레일링 호출을 줄여 일일 요청한도 소모를 낮춘다(2026-09-13 초과 사고 조사 결과).
            "pagination": {"page_param": "pageNo", "total_path": "$.response.body.totalCount", "max_pages": 50},
        },
        "field_maps": [
            ("notice_no", "$.bidNtceNo", None),
            ("title", "$.bidNtceNm", None),
            ("org_name", "$.ntceInsttNm", None),
            ("open_dt", "$.bidBeginDt", "%Y-%m-%d %H:%M:%S"),  # 2026-09-05, 용역과 동일 이유
            ("close_dt", "$.bidClseDt", "%Y-%m-%d %H:%M:%S"),
            ("est_price", "$.presmptPrce", None),
            ("url", "$.bidNtceDtlUrl", None),
            ("extra:bidNtceDt", "$.bidNtceDt", None),
            ("extra:cntrctCnclsMthdNm", "$.cntrctCnclsMthdNm", None),
            ("extra:opengDt", "$.opengDt", None),
            ("extra:cnstrtsiteRgnNm", "$.cnstrtsiteRgnNm", None),  # 공사현장지역(공사 전용)
        ],
    },
    # 2026-09-04 — 발주계획 3종 신규 등록. url=orderPlanDtlUrl(전 biz_type 공통, 실측 확인).
    # 첨부파일: API 응답에 atchFileExistnceYn 플래그만 있고 실제 다운로드 URL 필드가 없다(실측
    # 248건 전수 확인, "Y" 사례 0건) — 첨부파일을 보려면 orderPlanDtlUrl 상세페이지를 열어야
    # 하는데 g2b.go.kr이 WebSquare SPA라 정적 스크래핑이 안 됨(조사 완료). 이 소스는 목록·상세
    # 필드까지만 등록하고, 첨부파일 수집은 Playwright 도입(별도 결정) 이후로 미룬다.
    #
    # 2026-09-05 — open_dt(구 nticeDt) 매핑 제거(사용자 발견) — nticeDt는 "이 발주계획이
    # 등록된 날"일 뿐 실제 발주/입찰 시작일이 아니라, open_dt로 쓰면 등록되자마자 "입찰접수
    # 중"으로 잘못 표시됐다(발주계획 820건 중 547건). 발주계획 단계엔 정식 시작일 자체가
    # 없는 게 맞으므로 open_dt를 비워 자연히 "입찰미정"이 되게 한다 — nticeDt는 참고용으로
    # extra에 남긴다. date_range_params로 서버가 이미 기간을 걸러주므로 open_dt가 없어도
    # 수집 범위 필터링엔 지장 없음.
    "나라장터 발주계획현황서비스(용역)": {
        "config": {
            "endpoint": "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService/getOrderPlanSttusListServc",
            "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
            "date_range_params": {"begin": "inqryBgnDate", "end": "inqryEndDate", "format": "%Y%m%d"},
            "items_path": "$.response.body.items[*]",
            "biz_type": "용역",
            # 2026-09-04 실측 — 60일 범위는 정상(입찰공고와 달리 범위 초과 에러 없음)이나 페이지당
            # 100건 고정이라 pagination 없이는 1페이지만 가져온다(60일치 338건 확인, 100건만
            # 저장되고 나머지 238건 누락되던 버그).
            # 2026-09-05 — 나라장터 전체를 7일로 통일(사용자 지시, 입찰공고정보서비스 12,292건
            # 실측 계기).
            "max_lookback_days": 7,
            # 2026-09-14 — total_path 추가(response.body.totalCount 실측 확인) — 불필요한
            # 트레일링 호출을 줄여 일일 요청한도 소모를 낮춘다(2026-09-13 초과 사고 조사 결과).
            "pagination": {"page_param": "pageNo", "total_path": "$.response.body.totalCount", "max_pages": 50},
        },
        "field_maps": [
            ("title", "$.bizNm", None),
            ("org_name", "$.orderInsttNm", None),
            ("url", "$.orderPlanDtlUrl", None),
            ("extra:nticeDt", "$.nticeDt", None),  # 등록일(참고용, 입찰 시작일 아님)
            ("extra:orderPlanUntyNo", "$.orderPlanUntyNo", None),
            ("extra:prcrmntMethd", "$.prcrmntMethd", None),  # 조달방식
            ("extra:sumOrderAmt", "$.sumOrderAmt", None),  # 발주예정금액
        ],
    },
    "나라장터 발주계획현황서비스(물품)": {
        "config": {
            "endpoint": "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService/getOrderPlanSttusListThng",
            "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
            "date_range_params": {"begin": "inqryBgnDate", "end": "inqryEndDate", "format": "%Y%m%d"},
            "items_path": "$.response.body.items[*]",
            "biz_type": "물품",
            # 2026-09-14 — total_path 추가(response.body.totalCount 실측 확인) — 불필요한
            # 트레일링 호출을 줄여 일일 요청한도 소모를 낮춘다(2026-09-13 초과 사고 조사 결과).
            "pagination": {"page_param": "pageNo", "total_path": "$.response.body.totalCount", "max_pages": 50},
        },
        "field_maps": [
            ("title", "$.bizNm", None),
            ("org_name", "$.orderInsttNm", None),
            ("url", "$.orderPlanDtlUrl", None),
            ("extra:nticeDt", "$.nticeDt", None),
            ("extra:orderPlanUntyNo", "$.orderPlanUntyNo", None),
            ("extra:prcrmntMethd", "$.prcrmntMethd", None),
            ("extra:sumOrderAmt", "$.sumOrderAmt", None),
        ],
    },
    "나라장터 발주계획현황서비스(공사)": {
        "config": {
            "endpoint": "https://apis.data.go.kr/1230000/ao/OrderPlanSttusService/getOrderPlanSttusListCnstwk",
            "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
            "date_range_params": {"begin": "inqryBgnDate", "end": "inqryEndDate", "format": "%Y%m%d"},
            "items_path": "$.response.body.items[*]",
            "biz_type": "공사",
            # 2026-09-14 — total_path 추가(response.body.totalCount 실측 확인) — 불필요한
            # 트레일링 호출을 줄여 일일 요청한도 소모를 낮춘다(2026-09-13 초과 사고 조사 결과).
            "pagination": {"page_param": "pageNo", "total_path": "$.response.body.totalCount", "max_pages": 50},
        },
        "field_maps": [
            ("title", "$.bizNm", None),
            ("org_name", "$.orderInsttNm", None),
            ("url", "$.orderPlanDtlUrl", None),
            ("extra:nticeDt", "$.nticeDt", None),
            ("extra:orderPlanUntyNo", "$.orderPlanUntyNo", None),
            ("extra:prcrmntMethd", "$.prcrmntMethd", None),
            ("extra:sumOrderAmt", "$.sumOrderAmt", None),
        ],
    },
    # 2026-09-05 — 사전규격 3종 등록(보류 해제, 사용자 지시). 등록 당시엔 이 서비스가 주는
    # 상세페이지 URL이 없어 첨부파일 다운로드 URL(specDocFileUrl1)로 대신했었는데, 2026-09-10
    # 사용자가 실제 브라우저에서 진짜 상세페이지 URL 패턴을 직접 확인해줬다 —
    # `https://www.g2b.go.kr/link/PRVA004_02/?bfSpecRegNo={사전규격등록번호}`(로그인 불필요,
    # 발주계획의 orderPlanDtlUrl과 같은 성격). 응답 필드명은 `bfSpecRgstNo`(Rgst)인데 이
    # URL의 쿼리 파라미터명은 `bfSpecRegNo`(Reg)로 철자가 달라 헷갈리기 쉬우니 주의(의사결정_로그
    # 참고). urlfmt: 템플릿(mapper._resolve, IRIS·K-water에 이미 쓰던 것과 동일한 메커니즘)으로
    # 조립한다.
    # date_range_params 60일 요청도 에러 없이 정상 응답함을 확인(입찰공고정보서비스와 달리 이
    # 서비스엔 30일 상한이 없음) — 단 물량이 매우 많아(30일 기준 용역 4,763건·물품 4,968건·
    # 공사 246건) 초기 백필은 --max-lookback-days를 짧게 잡아서 돈다(운영 가이드, 코드 아님).
    #
    # open_dt/close_dt는 매핑하지 않는다(2026-09-05, 사용자 발견) — rcptDt는 "사전규격이
    # 등록된 날", opninRgstClseDt는 "의견수렴 마감일"일 뿐 둘 다 "입찰 시작/마감"이 아니다.
    # 매핑해두면 등록되자마자 "입찰접수 중"으로, 의견수렴이 끝나면 "입찰마감"으로 잘못
    # 표시된다(실측: 사전규격 1,284건 중 1,272건). 정식 입찰 시작일 자체가 없는 단계이므로
    # open_dt를 비워 자연히 "입찰미정"이 되게 하고, 원래 날짜는 참고용으로 extra에 남긴다.
    "나라장터 사전규격정보서비스(용역)": {
        "config": {
            "endpoint": "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc",
            "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
            "date_range_params": {"begin": "inqryBgnDt", "end": "inqryEndDt", "format": "%Y%m%d%H%M"},
            "items_path": "$.response.body.items[*]",
            "biz_type": "용역",
            # 2026-09-05 — 나라장터 전체를 7일로 통일(사용자 지시).
            "max_lookback_days": 7,
            # 2026-09-14 — total_path 추가(response.body.totalCount 실측 확인) — 불필요한
            # 트레일링 호출을 줄여 일일 요청한도 소모를 낮춘다(2026-09-13 초과 사고 조사 결과).
            "pagination": {"page_param": "pageNo", "total_path": "$.response.body.totalCount", "max_pages": 60},
        },
        "field_maps": [
            ("notice_no", "$.bfSpecRgstNo", None),
            ("title", "$.prdctClsfcNoNm", None),
            ("org_name", "$.orderInsttNm", None),
            ("url", "urlfmt:https://www.g2b.go.kr/link/PRVA004_02/?bfSpecRegNo={bfSpecRgstNo}", None),
            ("extra:rcptDt", "$.rcptDt", None),  # 사전규격 등록일(참고용)
            ("extra:opninRgstClseDt", "$.opninRgstClseDt", None),  # 의견수렴 마감일(참고용)
            ("extra:refNo", "$.refNo", None),  # 내부관리번호
            ("extra:swBizObjYn", "$.swBizObjYn", None),  # SW사업대상여부
        ],
    },
    "나라장터 사전규격정보서비스(물품)": {
        "config": {
            "endpoint": "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoThng",
            "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
            "date_range_params": {"begin": "inqryBgnDt", "end": "inqryEndDt", "format": "%Y%m%d%H%M"},
            "items_path": "$.response.body.items[*]",
            "biz_type": "물품",
            # 2026-09-14 — total_path 추가(response.body.totalCount 실측 확인) — 불필요한
            # 트레일링 호출을 줄여 일일 요청한도 소모를 낮춘다(2026-09-13 초과 사고 조사 결과).
            "pagination": {"page_param": "pageNo", "total_path": "$.response.body.totalCount", "max_pages": 60},
        },
        "field_maps": [
            ("notice_no", "$.bfSpecRgstNo", None),
            ("title", "$.prdctClsfcNoNm", None),
            ("org_name", "$.orderInsttNm", None),
            ("url", "urlfmt:https://www.g2b.go.kr/link/PRVA004_02/?bfSpecRegNo={bfSpecRgstNo}", None),
            ("extra:rcptDt", "$.rcptDt", None),
            ("extra:opninRgstClseDt", "$.opninRgstClseDt", None),
            ("extra:refNo", "$.refNo", None),
            ("extra:swBizObjYn", "$.swBizObjYn", None),
        ],
    },
    "나라장터 사전규격정보서비스(공사)": {
        "config": {
            "endpoint": "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoCnstwk",
            "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
            "date_range_params": {"begin": "inqryBgnDt", "end": "inqryEndDt", "format": "%Y%m%d%H%M"},
            "items_path": "$.response.body.items[*]",
            "biz_type": "공사",
            # 2026-09-14 — total_path 추가(response.body.totalCount 실측 확인) — 불필요한
            # 트레일링 호출을 줄여 일일 요청한도 소모를 낮춘다(2026-09-13 초과 사고 조사 결과).
            "pagination": {"page_param": "pageNo", "total_path": "$.response.body.totalCount", "max_pages": 60},
        },
        "field_maps": [
            ("notice_no", "$.bfSpecRgstNo", None),
            ("title", "$.prdctClsfcNoNm", None),
            ("org_name", "$.orderInsttNm", None),
            ("url", "urlfmt:https://www.g2b.go.kr/link/PRVA004_02/?bfSpecRegNo={bfSpecRgstNo}", None),
            ("extra:rcptDt", "$.rcptDt", None),
            ("extra:opninRgstClseDt", "$.opninRgstClseDt", None),
            ("extra:refNo", "$.refNo", None),
            ("extra:swBizObjYn", "$.swBizObjYn", None),
        ],
    },
    # advisory INBOX #2(2026-09-01) 필드명 추정을 2026-09-02 실제 서비스키로 라이브 검증·정정함
    # (`advisory/공공데이타/공공데이터_인증_key_260902_*.xlsx`의 실키 사용) — ⚠️ **`type=json`을
    # 보내도 실제로는 XML만 응답**(어댑터에 XML 지원 추가, format:"xml"). items_path는
    # `response.body.items.item[*]`가 맞고(items 태그 밑에 item 반복 + numOfRows/pageNo/
    # totalCount가 형제로 같이 옴), pressDt는 대시 포함 `YYYY-MM-DD` 형식(원안은 `%Y%m%d`로
    # 틀렸었음). 응답에 실제로 `managerName`·`managerTel`(담당자 실명·전화번호)이 있음을
    # 확인 — field_maps에서 매핑하지 않아 제외됨(설계 의도대로 동작 확인, INBOX #8).
    # close_dt 매핑이 없다 — 이 소스엔 마감일 항목 자체가 없음(INBOX #1, 의도적으로 비움).
    "과학기술정보통신부 사업공고(부처 자체, 범부처 아님)": {
        "config": {
            "endpoint": "https://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList",
            "format": "xml",
            "params": {"type": "json", "numOfRows": "100", "pageNo": "1"},
            "items_path": "$.response.body.items.item[*]",
        },
        "field_maps": [
            ("title", "$.subject", None),
            ("org_name", "const:과학기술정보통신부", None),
            ("open_dt", "$.pressDt", "%Y-%m-%d"),
            ("url", "$.viewUrl", None),
            ("extra:deptName", "$.deptName", None),  # 소관부서명(조직 단위) — 개인정보 아님
        ],
    },
    # 2026-09-03 실측(위 K-water base_url 주석 참고). 3개 오퍼레이션(입찰공고/사전규격공개/
    # 발주계획) 중 상세페이지 URL을 확인한 건 "내자 입찰공고 정보 조회"(dmscptList) 하나뿐이라
    # 이것만 등록한다 — 나머지 둘(사전규격공개·발주계획)은 응답에 URL 필드가 없어 상세URL 패턴을
    # 못 찾으면 notice.url(NOT NULL)을 못 채운다, 조사 후 별도 소스로 추가 예정.
    # 상세URL은 웹검색으로 발견한 단축 링크 패턴(`ebid.kwater.or.kr/fz?bidno=`)으로 조립 —
    # 구글에 색인된 실제 사례(제목이 "입찰공고상세 [공고번호]"로 정확히 매칭됨)로 검증함.
    "K-water 입찰공고": {
        "config": {
            "endpoint": "http://opendata.kwater.or.kr/openapi-data/service/pubd/ebid/tndr/dmscpt/list",
            "params": {"_type": "json", "numOfRows": "100", "pageNo": "1"},
            "month_param": "searchDt",  # begin/end 쌍이 아니라 검색년월(YYYYMM) 하나만 받음
            "items_path": "$.response.body.items.item[*]",
        },
        "field_maps": [
            ("notice_no", "$.tndrPbanno", None),
            ("title", "$.tndrPblancNm", None),
            ("org_name", "const:한국수자원공사", None),
            ("open_dt", "$.tndrPblancDe", "%Y%m%d"),
            ("close_dt", "$.tndrPblancEnddt", "%Y%m%d"),  # 값 없으면 "-" — 마감일 미공개로 처리됨
            ("est_price", "$.tndrPlnprc", None),
            ("url", "urlfmt:https://ebid.kwater.or.kr/fz?bidno={tndrPbanno}", None),
            ("extra:cntrctDeptNm", "$.cntrctDeptNm", None),  # 부서명 — 개인정보 아님
            ("extra:ctrmthdCdNm", "$.ctrmthdCdNm", None),  # 계약방법
            ("extra:tndrStat", "$.tndrStat", None),  # 진행상태
            # intnChargerNm(담당자 실명)은 의도적으로 매핑하지 않음 — PII, _PII_KEY_PATTERN의
            # "charger"가 애초에 매핑 시도해도 validate_field_maps가 거부함.
        ],
    },
    # advisory INBOX #3(2026-09-01) — 필드명·엔드포인트는 실제 POST 호출로 직접 확인함(서비스키
    # 불필요, 공개 JSON 응답). advisory 원안은 "GET·html·서버렌더링"이었으나 검증 결과 정정 —
    # 실제로는 페이지 자체(GET)는 빈 템플릿만 오고, 진짜 데이터는 이 엔드포인트를 폼바디 POST로
    # 불러야 나온다(그래서 어댑터를 openapi로 재분류). 상세 URL은 응답에 없어 ancmId로 조립.
    #
    # 2026-09-04 버그 수정(의사결정_로그) — 원래 의도(INBOX #3: "접수중·마감은 범위 아님")대로면
    # ancmPrg="ancmPre"(접수예정 탭)를 보내야 하는데, params에 이 키 자체가 빠져 있어 서버가
    # 히든필드 기본값(ancmIng=접수중)으로 응답해왔다 — "IRIS 접수예정"이라는 이름과 반대로
    # 실제로는 접수중 공고만 수집해온 것을 라이브 재현으로 확인. 실제 사이트의 탭 전환
    # onclick(f_bsnsAncmListForm_go)이 쓰는 값(ancmPre/ancmIng/ancmEnd)을 그대로 사용해 수정.
    # ancmPre 전체는 554페이지(약 5,540건, 등록일 기준 내림차순 정렬 — 페이지 1은 2026-09-01,
    # 페이지 2부터 2025-12-23으로 바로 떨어짐. IRIS 공모예고처럼 등록순서라 정렬이 어긋나는
    # 문제는 없어 전 페이지 스캔이 필요 없다) 중 최근 2개월치만 있으면 되므로 max_pages를
    # 낮게(15) 유지한다.
    "IRIS 접수예정": {
        "config": {
            "endpoint": "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do",
            "method": "POST",
            "params": {
                "pageIndex": "1", "prgmId": "", "pbofrTpArr": "", "ancmSttArr": "",
                "blngGovdSeArr": "", "sorgnIdArr": "", "qualCndtArr": "", "techFildArr": "",
                "ancmPrg": "ancmPre",
            },
            "items_path": "$.listBsnsAncmBtinSitu[*]",
            # 2026-09-02 — IRIS는 날짜범위 파라미터를 안 받는다(공고일 기준 요청 필터 자체가
            # 없음, techFildArr 등은 분야 필터일 뿐). 대신 pageIndex로만 넘어가고 응답의
            # paginationInfo.totalPageCount로 전체 페이지 수를 알 수 있어, 전 페이지를 받은 뒤
            # runner._collection_window()가 계산한 begin(2개월 캡)으로 클라이언트측에서 자른다.
            "pagination": {"page_param": "pageIndex", "total_path": "$.paginationInfo.totalPageCount", "max_pages": 15},
        },
        "field_maps": [
            ("notice_no", "$.ancmNo", None),
            ("title", "$.ancmTl", None),
            ("org_name", "$.sorgnNm", None),
            # 2026-09-05 — open_dt를 ancmDe(공고 등록일)에서 rcveStrDe(접수시작일)로 교체
            # (사용자 발견) — ancmDe는 이 공고가 IRIS에 등록된 날일 뿐이라 항상 과거값이고,
            # "접수예정"이라는 이름과 반대로 실제로는 "입찰예정" 상태가 절대 안 나왔다.
            # rcveStrDe(실측: "2026.09.08" 형식, 실제 미래 날짜 확인됨)가 진짜 접수 시작일 —
            # 값이 없는 항목(구체적 시작일 미정)은 open_dt가 비어 자연히 "입찰미정"이 된다.
            ("open_dt", "$.rcveStrDe", "%Y.%m.%d"),
            ("close_dt", "$.rcveEndDe", "%Y.%m.%d"),
            ("url", "urlfmt:https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId={ancmId}", None),
            # 2026-09-02 — 명명 컬럼에 안 들어가는 나머지 필드(공모유형·소관부처·접수상태·D-day
            # 등)를 notice.extra에 담아 화면 카드에 보여준다(전부 목록 응답에 이미 있던 값 —
            # 사업담당자·연락처 같은 개인정보는 상세페이지에만 있고 목록 응답엔 없음을 직접
            # 확인함, 그래도 mapper.validate_field_maps가 재차 걸러줌).
            ("extra:ancmDe", "$.ancmDe", None),  # 공고 등록일(참고용, open_dt 아님)
            ("extra:dDay", "$.dDay", None),
            ("extra:rcveStt", "$.rcveStt", None),
            ("extra:rcveSttSeNmLst", "$.rcveSttSeNmLst", None),
            ("extra:sorgnId", "$.sorgnId", None),
            ("extra:blngGovdSe", "$.blngGovdSe", None),
            ("extra:blngGovdSeNm", "$.blngGovdSeNm", None),
            ("extra:budJuriGovdSe", "$.budJuriGovdSe", None),
            ("extra:pbofrTpSeLst", "$.pbofrTpSeLst", None),
            ("extra:pbofrTpSeNmLst", "$.pbofrTpSeNmLst", None),
        ],
    },
    # 2026-09-05 — "접수중"(ancmPrg=ancmIng) 탭. 필드매핑은 접수예정과 완전히 동일(같은
    # 엔드포인트·같은 응답 스키마), ancmPrg 값만 다르다. 실측(2026-09-04) 기준 이 탭은
    # totalPageCount가 2뿐이라(약 15~20건) max_pages를 낮게 유지해도 전량 커버된다.
    "IRIS 접수중": {
        "config": {
            "endpoint": "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do",
            "method": "POST",
            "params": {
                "pageIndex": "1", "prgmId": "", "pbofrTpArr": "", "ancmSttArr": "",
                "blngGovdSeArr": "", "sorgnIdArr": "", "qualCndtArr": "", "techFildArr": "",
                "ancmPrg": "ancmIng",
            },
            "items_path": "$.listBsnsAncmBtinSitu[*]",
            "pagination": {"page_param": "pageIndex", "total_path": "$.paginationInfo.totalPageCount", "max_pages": 10},
        },
        "field_maps": [
            ("notice_no", "$.ancmNo", None),
            ("title", "$.ancmTl", None),
            ("org_name", "$.sorgnNm", None),
            ("open_dt", "$.rcveStrDe", "%Y.%m.%d"),  # 2026-09-05, 접수예정과 동일 이유
            ("close_dt", "$.rcveEndDe", "%Y.%m.%d"),
            ("url", "urlfmt:https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId={ancmId}", None),
            ("extra:ancmDe", "$.ancmDe", None),
            ("extra:dDay", "$.dDay", None),
            ("extra:rcveStt", "$.rcveStt", None),
            ("extra:rcveSttSeNmLst", "$.rcveSttSeNmLst", None),
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
            # 2026-09-05 — 다른 소스와 달리 open_dt=regDt(등록일)를 그대로 둔다. 정확히는
            # 사전규격·발주계획과 같은 문제(regDt가 "입찰 시작일"이 아니라 등록일)가 있지만,
            # 이 소스엔 date_range_params가 없어(위 주석 — IRIS는 날짜범위 파라미터를 안 받음)
            # 서버가 기간을 안 걸러주고 open_dt로 클라이언트측 기간 필터링(_collection_window)
            # 을 하고 있다. open_dt를 비우면 65페이지(591건) 전체가 매번 걸러지지 않고 들어와
            # 버린다 — 이 소스 하나뿐인 낮은 우선순위 이슈라 지금은 상태 표시 정확도보다
            # 수집 범위 제어를 우선한다(알려진 한계로 남김).
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
    # 2026-09-13 — html 어댑터(app/collector/adapters/html.py) 첫 도입. 목록 페이지(GET,
    # fromDate/endDate로 날짜범위, pageIndex로 페이지네이션) 표 한 행이 공고구분/공고번호/
    # 공고명(+상세 파라미터가 담긴 링크)/금액/공고게시일/개찰예정일/처리상태 7개 셀 — 직접
    # 확인(2026-09-13). notice.biz_type 컬럼은 소스 단위 상수만 지원해(app/collector/runner.py
    # `cfg["config"].get("biz_type")`) 공고구분(용역/구매/공사/물품 혼재)을 담을 수 없으므로
    # extra:biz_type_raw로 원문을 보존한다. 발주기관은 이 소스 전체가 항상 국가철도공단 하나뿐이라
    # const:로 고정(과학기술정보통신부 사업공고와 동일 패턴, advisory INBOX #2). 첨부파일 다운로드는
    # 이번 범위 밖(A1 첨부분석은 g2b/IRIS 전용 핸들러만 있어 이 소스는 항상 "첨부 0건"으로 끝남 —
    # 필요해지면 별도 작업으로 추가).
    # 2026-09-15 — 사용자 지시: "용역", "입찰"만 수집/분석하도록. 목록 페이지의 "공고구분"
    # 드롭다운(ggGubunS)이 서버측 필터를 지원함을 직접 확인(값: 01=공사, 02=용역, 03=구매,
    # 04=물품, 빈 값=전체) — ggGubunS=02로 보내면 실제로 용역만 내려옴을 라이브 호출로 검증.
    # 이 사이트는 애초에 게시판 전체가 "입찰공고"라 "입찰" 조건은 이미 항상 충족된다.
    "국가철도공단 입찰공고": {
        "config": {
            "endpoint": "https://ebid.kr.or.kr/bid/anc/bidAncList.do",
            "params": {"menuNo": "14000", "ggGubunS": "02"},
            "date_range_params": {"begin": "fromDate", "end": "endDate", "format": "%Y-%m-%d"},
            "pagination": {"page_param": "pageIndex", "max_pages": 60},
            "table_class": "tbl01",
            "columns": ["biz_type_raw", "notice_no", "title", "est_price", "open_dt", "close_dt", "status"],
            "detail_link_column_index": 2,
            "detail_endpoint": "https://ebid.kr.or.kr/bid/anc/bidAncDetail.do",
            "detail_param_names": [
                "gyErBeonho", "crSangtae", "ggDrIrja", "ggNyeondo", "ggIrBeonho",
                "ygGeumaeg", "ggChasu", "cjbcDrMyeong", "irBeonho", "ggGubun",
            ],
        },
        "field_maps": [
            ("title", "$.title", None),
            ("org_name", "const:국가철도공단", None),
            ("url", "$.url", None),
            ("notice_no", "$.notice_no", None),
            ("est_price", "$.est_price", None),
            ("open_dt", "$.open_dt", "%Y-%m-%d"),
            ("close_dt", "$.close_dt", "%Y-%m-%d"),
            ("extra:biz_type_raw", "$.biz_type_raw", None),
            ("extra:status", "$.status", None),
        ],
    },
    # 2026-09-14 — 목록 표(class="tl") 한 행 8개 셀을 실측 확인(입찰번호/입찰명(+상세 파라미터가
    # 담긴 javascript:viewBid(notice_code,bid_code,round,type) 링크)/입찰구분/업무구분/
    # 계약방법/입찰마감일시/개찰일시/취소여부). 상세 페이지는 GET 쿼리스트링으로도 그대로 열림을
    # 확인(POST 폼 제출 없이도 동작, curl로 직접 검증) — viewBid의 4번째 인자(type)는 게시판이
    # bidsale/수소공고 등 드문 유형일 때 다른 JSP로 보내는 용도라 URL 조립엔 앞 3개만 쓴다
    # (app/collector/adapters/html.py의 detail_param_names가 args보다 적어도 허용하도록 수정).
    # est_price(예정가격)는 이 목록 표에 없음 — 상세 페이지에만 있어 이번 범위에서는 비워둔다
    # (est_price 자체가 REQUIRED_FIELDS가 아니므로 문제 없음). 인코딩은 EUC-KR이나 서버가
    # Content-Type 헤더에 명시해 requests가 자동으로 올바르게 디코딩함(2026-09-14 실측 확인).
    # 2026-09-15 — 사용자 지시: "용역", "입찰"만 수집/분석하도록. 목록 페이지의 "업무구분"
    # 드롭다운(worktype)이 서버측 필터를 지원함을 직접 확인(값: C=공사, S=용역, M=물품(내자),
    # F=물품(외자), 빈 값=전체) — worktype=S로 라이브 호출해 실제로 용역만 내려옴을 검증.
    # 이 게시판 자체가 전부 "입찰공고"라 "입찰" 조건은 이미 항상 충족된다.
    "한국가스공사 입찰공고": {
        "config": {
            "endpoint": "https://bid.kogas.or.kr:9443/supplier/contents/bid/bid_list_notice_frm.jsp",
            "params": {"worktype": "S", "title": "", "e_startday": "", "e_endday": "", "o_startday": "", "o_endday": "", "orderplace": "", "reqbidno": ""},
            "pagination": {"page_param": "page", "max_pages": 5},
            "table_class": "tl",
            "columns": [
                "notice_no", "title", "extra_bid_type", "biz_type_raw",
                "extra_contract_method", "close_dt", "extra_openg_dt", "extra_cancelled",
            ],
            "detail_link_column_index": 1,
            "detail_endpoint": "https://bid.kogas.or.kr:9443/supplier/contents/bid/bid_detail_view_notice.jsp",
            "detail_js_function": "viewBid",
            "detail_param_names": ["notice_code", "bid_code", "round"],
        },
        "field_maps": [
            ("title", "$.title", None),
            ("org_name", "const:한국가스공사", None),
            ("url", "$.url", None),
            ("notice_no", "$.notice_no", None),
            ("close_dt", "$.close_dt", "%Y.%m.%d %H:%M"),
            ("extra:biz_type_raw", "$.biz_type_raw", None),
            ("extra:bid_type", "$.extra_bid_type", None),
            ("extra:contract_method", "$.extra_contract_method", None),
            ("extra:opengDt", "$.extra_openg_dt", None),
            ("extra:cancelled", "$.extra_cancelled", None),
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
