"""나라장터 g2b 계열(입찰공고·사전규격·발주계획) 첨부(또는 인라인 텍스트) 발견 로직.

analysis_pilot.py의 500줄 상한을 넘겨 분리했다(2026-09-08, CLAUDE.md 파일당 500줄 규칙).
g2b 목록 API는 하위 3계열이 있고 첨부를 표현하는 방식이 계열마다 다르다(2026-09-06 실측,
2026-09-08 공식 명세서 심층분석으로 보강):
  - 입찰공고정보서비스(BidPublicInfoService): ntceSpecDocUrl1~10 + ntceSpecFileNm1~10(공고
    규격서), sptDscrptDocUrl1~5(현장설명서, 파일명 필드 없음), stdNtceDocUrl(표준공고서 1건)
  - 사전규격정보서비스(HrcspSsstndrdInfoService): specDocFileUrl1~5뿐, 파일명 필드가 없음
    (명세서 확인 완료 — 6번째 슬롯·파일명/크기 필드는 애초에 존재하지 않음)
  - 발주계획현황서비스(OrderPlanSttusService): 목록 조회 응답엔 다운로드 URL이 없고 규격
    내용을 specCntnts/specItemNm·Cntnts1~5에 텍스트로 직접 준다(대부분 공백, 2026-09-08
    실측). 명세서 문서엔 첨부파일 전용 오퍼레이션(getOrderPlanSttusAtchFileList)이 있다고
    적혀 있었으나, 사용자가 data.go.kr 마이페이지(활용신청 상세기능정보)를 직접 확인한 결과
    등록된 오퍼레이션 8개 중에 없음을 확인 — 문서가 앞서갔을 뿐 실제로는 미제공(의사결정_로그
    88번). 첨부파일은 API로는 확보 불가, 상세페이지(JS 필수) 스크래핑만 남은 방법이라 헤드리스
    브라우저 도입 여부를 사용자가 검토 중(구현스펙.md 향후 과제 참고).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.collector.adapters.openapi import fetch_openapi_items
from app.models import raw_payload, source_config, source_credential

_G2B_BID_FIELD_PAIRS = 10  # ntceSpecDocUrl1~10 / ntceSpecFileNm1~10
_G2B_BID_SITE_DESCRIPTION_COUNT = 5  # sptDscrptDocUrl1~5(현장설명서, 파일명 필드 없음)
_G2B_PRESTANDARD_FIELD_COUNT = 5  # specDocFileUrl1~5
_G2B_LIVE_LOOKUP_WINDOW_DAYS = 14  # 공고 게시일 앞뒤로 이 폭만큼만 목록 API를 재조회(전체 재수집 아님)

# 파일명에 이 키워드가 있으면 "대부분의 과제에서 공통되는" 문서로 보고 분석 대상에서 뺀다
# (2026-09-05 최초 지시, 2026-09-08 사용자가 기준을 명확히 재정의 — "제출서류·규정·법령·
# 문서 양식·사용법·매뉴얼은 대부분 과제 공통이라 제외, 공고·기획서·개요서·과업지시서·RFP·
# 지표는 꼭 분석해야 함"). 새 패턴이 발견되면 여기만 추가하면 된다.
_SKIP_NAME_KEYWORDS = (
    "양식", "이의신청서", "관련법령", "매뉴얼", "자율성트랙", "사전지원제외", "국제공동r&d",
    "제출서류", "규정", "법령", "사용법",
)


def _normalize_for_match(text: str) -> str:
    """공백을 없애고 소문자로 — 실제 파일명은 "관련 법령"처럼 키워드 중간에 띄어쓰기가
    들어간 경우가 흔해(2026-09-05 실측, 로봇산업기술개발사업 공고 첨부) 그대로 부분일치하면
    놓친다."""
    return re.sub(r"\s+", "", text).lower()


def _should_skip_by_name(filename: str) -> bool:
    normalized = _normalize_for_match(filename)
    return any(_normalize_for_match(keyword) in normalized for keyword in _SKIP_NAME_KEYWORDS)


def _fetch_g2b_live_item(
    conn: Connection, source_id: int, match_field: str, match_value: str | None, anchor_dt: datetime | None
) -> dict | None:
    """caching된 raw_payload가 아니라 원래 수집에 쓰는 목록 오픈API를 이 자리에서 다시 호출해
    공고 원본 항목 하나를 가져온다(2026-09-06 — 캐시가 비어 있어도 안전하게 만들기 위해).
    실패는 여기서 삼키지 않는다 — 호출부(run_extraction_pilot)가 분석을 failed로 남기고
    사유를 verdict에 적어야 "조용한 빈 결과"가 안 된다(CLAUDE.md S8)."""
    if not match_value:
        return None
    cfg = conn.execute(
        select(source_config.c.config).where(source_config.c.source_id == source_id).order_by(source_config.c.ver.desc()).limit(1)
    ).scalar_one_or_none()
    if cfg is None:
        return None
    service_key = conn.execute(
        select(source_credential.c.value).where(
            source_credential.c.source_id == source_id, source_credential.c.kind == "service_key"
        )
    ).scalar_one_or_none()
    anchor = anchor_dt or datetime.now(timezone.utc)
    window = timedelta(days=_G2B_LIVE_LOOKUP_WINDOW_DAYS)
    items = fetch_openapi_items(cfg, service_key, begin=anchor - window, end=anchor + window)
    return next((i for i in items if i.get(match_field) == match_value), None)


def _fetch_g2b_cached_item(conn: Connection, source_id: int, match_field: str, match_value: str | None) -> dict | None:
    """이 소스가 과거 수집 때마다 raw_payload에 남겨둔 원본 API 응답 스냅샷에서 찾는다
    (2026-09-09, 사용자 지적 — "재분석"·오래된 백로그 처리가 여전히 이 공고 하나 때문에
    목록 API를 통째로 재호출하고 있었다, 82번 항목에서 "방금 수집한 공고"만 먼저 고쳤던
    빈틈). g2b는 매 수집마다 raw_payload를 남기므로(app/collector/runner.py) 대부분의
    경우 여기서 찾아지고, 그러면 apis.data.go.kr을 아예 안 부른다 — 캐시에 없을 때만
    (예: 이 소스가 실제로 한 번도 이 공고를 다시 수집한 적 없는 아주 오래된 경우) 호출부가
    _fetch_g2b_live_item으로 폴백한다."""
    if not match_value:
        return None
    rows = conn.execute(
        select(raw_payload.c.body).where(raw_payload.c.source_id == source_id).order_by(raw_payload.c.fetched_at.desc())
    )
    for (body,) in rows:
        for item in body.get("items", []):
            if item.get(match_field) == match_value:
                return item
    return None


def _g2b_bid_attachments(item: dict) -> list[dict]:
    """입찰공고정보서비스 — 공고규격서(ntceSpecDocUrl1~10 + ntceSpecFileNm1~10) +
    현장설명서(sptDscrptDocUrl1~5, 파일명 필드 없음) + 표준공고서(stdNtceDocUrl 1건) —
    2026-09-08 공식 명세서(v1.2) 확인, 뒤 2종은 그동안 놓치고 있었다."""
    found = []
    for i in range(1, _G2B_BID_FIELD_PAIRS + 1):
        url = item.get(f"ntceSpecDocUrl{i}")
        name = item.get(f"ntceSpecFileNm{i}")
        if url and name and not _should_skip_by_name(name):
            found.append({"name": name, "download_url": url, "inline_text": None})
    for i in range(1, _G2B_BID_SITE_DESCRIPTION_COUNT + 1):
        url = item.get(f"sptDscrptDocUrl{i}")
        if url:
            name = _filename_from_url(url, f"현장설명서{i}")
            if not _should_skip_by_name(name):
                found.append({"name": name, "download_url": url, "inline_text": None})
    std_notice_url = item.get("stdNtceDocUrl")
    if std_notice_url:
        name = _filename_from_url(std_notice_url, "표준공고서")
        if not _should_skip_by_name(name):
            found.append({"name": name, "download_url": std_notice_url, "inline_text": None})
    return found


def _filename_from_url(url: str, fallback: str) -> str:
    query = parse_qs(urlparse(url).query)
    for key in ("fileNm", "fileName"):
        if query.get(key):
            return query[key][0]
    return fallback


def _g2b_prestandard_attachments(item: dict) -> list[dict]:
    """사전규격정보서비스 — specDocFileUrl1~5뿐이고 파일명 필드가 없다(2026-09-06 실측,
    2026-09-08 공식 명세서로 재확인 — 6번째 슬롯·파일명/크기 필드는 애초에 정의돼 있지 않음).
    이름은 URL에서 못 뽑으면 순번으로 대체한다."""
    found = []
    for i in range(1, _G2B_PRESTANDARD_FIELD_COUNT + 1):
        url = item.get(f"specDocFileUrl{i}")
        if not url:
            continue
        name = _filename_from_url(url, f"규격서{i}")
        if not _should_skip_by_name(name):
            found.append({"name": name, "download_url": url, "inline_text": None})
    return found


def _g2b_orderplan_docs(item: dict) -> list[dict]:
    """발주계획현황서비스 — 목록조회 응답의 인라인 규격텍스트(specCntnts/specItemCntnts1~5)는
    실측상 거의 항상 공백이다(2026-09-08). 진짜 첨부파일 전용 오퍼레이션은 실제 서비스에
    없음을 확인(의사결정_로그 88번, 구현스펙.md 향후 과제) — 지금은 인라인 텍스트만 문서로
    남긴다."""
    found = []
    if item.get("specCntnts"):
        found.append({"name": "규격내용", "download_url": None, "inline_text": item["specCntnts"]})
    for i in range(1, 6):
        content = item.get(f"specItemCntnts{i}")
        if content:
            name = item.get(f"specItemNm{i}") or f"규격항목{i}"
            found.append({"name": name, "download_url": None, "inline_text": content})
    return found


# g2b 목록 API 엔드포인트에 이 문자열이 있으면 해당 계열로 처리한다(source_id를 하드코딩하지
# 않아야 물품/공사 등 같은 계열의 다른 biz_type 소스가 추가돼도 이 파일을 안 고쳐도 된다).
_G2B_FAMILIES = (
    ("BidPublicInfoService", "bidNtceNo", _g2b_bid_attachments),
    ("HrcspSsstndrdInfoService", "bfSpecRgstNo", _g2b_prestandard_attachments),
    ("OrderPlanSttusService", "orderPlanUntyNo", _g2b_orderplan_docs),
)


def _discover_g2b_attachments(
    conn: Connection,
    source_id: int,
    notice_no: str | None,
    extra: dict | None,
    anchor_dt: datetime | None,
    *,
    prefetched_item: dict | None = None,
) -> list[dict]:
    """g2b 계열 3종을 구분해 각자의 방식으로 첨부(또는 인라인 텍스트) 목록을 만든다.

    prefetched_item이 있으면(2026-09-08, 방금 수집한 공고 처리 시) 나라장터 목록 API를
    다시 호출하지 않고 그 항목을 그대로 쓴다 — 실측 발견: 수집 직후 첨부분석(process_new_
    notices)이 공고 한 건마다 목록 API를 다시 실시간 호출하고 있었는데(사전규격 223건이면
    223번), 이미 수집 시점에 똑같은 데이터를 한 번에 받아둔 걸 낭비하는 데다 apis.data.go.kr
    이 불안정한 날엔 재호출 다수가 실패해 "규격내용 없음"으로 조용히 처리되는 사고로 이어졌다
    (사용자가 실제 수집 결과로 확인). notice_no가 아직 없을 수도 있어 여기서도 방어적으로
    시도한다.

    prefetched_item이 없으면(오래된 백로그 재처리, 상세페이지 "재분석" 버튼 등) 2026-09-09부터
    raw_payload 캐시를 먼저 찾는다(_fetch_g2b_cached_item) — 사용자 지적: "1단계 목록조회와
    2단계 재조회가 같은 API 아니냐, 1단계만으로 다 되지 않나". 이 소스는 매 수집마다 raw_payload
    에 원본을 남기므로 대부분 캐시에서 찾아지고, apis.data.go.kr을 아예 안 부른다. 캐시에
    없을 때만(이 소스를 한 번도 다시 수집한 적 없는 경우 등) 기존처럼 실시간 재조회로 폴백한다."""
    cfg = conn.execute(
        select(source_config.c.config).where(source_config.c.source_id == source_id).order_by(source_config.c.ver.desc()).limit(1)
    ).scalar_one_or_none()
    endpoint = (cfg or {}).get("endpoint", "")

    for marker, match_field, handler in _G2B_FAMILIES:
        if marker not in endpoint:
            continue
        if prefetched_item is not None:
            return handler(prefetched_item)
        # 발주계획현황서비스는 notice_no가 안 채워진다(공고번호 자체가 없는 단계) —
        # extra.orderPlanUntyNo로 매칭한다.
        match_value = notice_no if match_field != "orderPlanUntyNo" else (extra or {}).get("orderPlanUntyNo")
        item = _fetch_g2b_cached_item(conn, source_id, match_field, match_value)
        if item is None:
            item = _fetch_g2b_live_item(conn, source_id, match_field, match_value, anchor_dt)
        return handler(item) if item is not None else []
    return []  # 알 수 없는 g2b 계열 — 첨부 없음으로 처리(0건은 정상 종료 상태로 이미 지원됨)
