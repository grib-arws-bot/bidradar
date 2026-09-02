"""openapi 어댑터 — 공공데이터포털 계열 REST API(설계안 04-1). U11 범위는 이 어댑터 하나뿐 —
feed/html은 실제로 필요해지는 U13(소스 등록 마법사)에서 채운다.

⚠️ 모든 외부 호출은 반드시 url_guard.fetch()를 거친다(CLAUDE.md — 예외 없음). requests를
직접 호출하는 우회 경로를 만들지 말 것.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from jsonpath_ng.ext import parse as jsonpath_parse

from app.security.url_guard import fetch


def _fetch_page(config: dict[str, Any], method: str, endpoint: str, params: dict) -> Any:
    if method == "POST":
        response = fetch(endpoint, method="POST", data=params)
    else:
        response = fetch(endpoint, params=params)
    return response.json()


def fetch_openapi_items(config: dict[str, Any], service_key: str | None, *, begin: datetime, end: datetime) -> list[dict]:
    """source_config.config(JSONB) 형태:
    {
      "endpoint": "https://apis.data.go.kr/1230000/ao/BidPublicInfoService/getBidPblancListInfoServc",
      "method": "GET",  # 생략 시 GET. "POST"면 params를 폼 바디로 보낸다(공공데이터포털 API가
                        # 아니라 IRIS처럼 서비스키 없는 내부 JSON 엔드포인트를 그대로 호출할 때 씀 —
                        # advisory INBOX #3, 2026-09-01 직접 확인
      "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
      "date_range_params": {"begin": "inqryBgnDt", "end": "inqryEndDt", "format": "%Y%m%d%H%M"},
      "items_path": "$.response.body.items[*]",
      "pagination": {  # 선택 — API가 날짜범위 파라미터를 안 받고(IRIS처럼) 페이지만 넘기는 경우.
        "page_param": "pageIndex",       # 요청 파라미터 중 페이지 번호로 쓸 키
        "total_path": "$.paginationInfo.totalPageCount",  # 첫 응답에서 전체 페이지 수를 읽는 JSONPath
        "max_pages": 20                  # 안전장치 — total_path가 없거나 이상해도 무한루프 방지
      }
    }

    begin/end 계산(직전 성공 수집 이후~지금, 이력 없으면 2개월 캡)은 이 어댑터가 아니라
    runner._collection_window()의 몫이다 — 어댑터는 "무슨 기간을 조회할지"를 모르는 순수
    호출기로 남겨야 새 소스 추가 시 이 파일을 고치지 않아도 된다(설계안 04-1).

    pagination도 "며칠치를 볼지"는 모른 채 "총 몇 페이지인지"만 안다 — 기간으로 자르는 건
    runner가 mapped 아이템의 open_dt로 한다(2026-09-02, IRIS 재수집 정확도 개선).
    """
    endpoint = config["endpoint"]
    method = config.get("method", "GET").upper()
    base_params = dict(config.get("params", {}))
    if service_key:
        base_params["ServiceKey"] = service_key

    date_range = config.get("date_range_params")
    if date_range:
        fmt = date_range.get("format", "%Y%m%d%H%M")
        base_params[date_range["begin"]] = begin.strftime(fmt)
        base_params[date_range["end"]] = end.strftime(fmt)

    items_path = config.get("items_path", "$.response.body.items[*]")
    items_expr = jsonpath_parse(items_path)

    pagination = config.get("pagination")
    if not pagination:
        payload = _fetch_page(config, method, endpoint, base_params)
        return [match.value for match in items_expr.find(payload)]

    page_param = pagination["page_param"]
    total_path = pagination.get("total_path")
    max_pages = pagination.get("max_pages", 20)
    total_expr = jsonpath_parse(total_path) if total_path else None

    all_items: list[dict] = []
    page = 1
    total_pages: int | None = None
    while page <= max_pages:
        params = dict(base_params)
        params[page_param] = str(page)
        payload = _fetch_page(config, method, endpoint, params)

        page_items = [match.value for match in items_expr.find(payload)]
        if not page_items:
            break
        all_items.extend(page_items)

        if total_pages is None and total_expr is not None:
            matches = total_expr.find(payload)
            total_pages = int(matches[0].value) if matches else None
        if total_pages is not None and page >= total_pages:
            break
        page += 1

    return all_items
