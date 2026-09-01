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


def fetch_openapi_items(config: dict[str, Any], service_key: str | None, *, begin: datetime, end: datetime) -> list[dict]:
    """source_config.config(JSONB) 형태:
    {
      "endpoint": "https://apis.data.go.kr/1230000/ao/BidPublicInfoService/getBidPblancListInfoServc",
      "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
      "date_range_params": {"begin": "inqryBgnDt", "end": "inqryEndDt", "format": "%Y%m%d%H%M"},
      "items_path": "$.response.body.items[*]"
    }

    begin/end 계산(직전 성공 수집 이후~지금, 이력 없으면 2개월 캡)은 이 어댑터가 아니라
    runner._collection_window()의 몫이다 — 어댑터는 "무슨 기간을 조회할지"를 모르는 순수
    호출기로 남겨야 새 소스 추가 시 이 파일을 고치지 않아도 된다(설계안 04-1).
    """
    endpoint = config["endpoint"]
    params = dict(config.get("params", {}))
    if service_key:
        params["ServiceKey"] = service_key

    date_range = config.get("date_range_params")
    if date_range:
        fmt = date_range.get("format", "%Y%m%d%H%M")
        params[date_range["begin"]] = begin.strftime(fmt)
        params[date_range["end"]] = end.strftime(fmt)

    response = fetch(endpoint, params=params)
    payload = response.json()

    items_path = config.get("items_path", "$.response.body.items[*]")
    expr = jsonpath_parse(items_path)
    return [match.value for match in expr.find(payload)]
