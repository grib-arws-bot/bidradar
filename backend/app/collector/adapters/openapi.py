"""openapi 어댑터 — 공공데이터포털 계열 REST API(설계안 04-1). U11 범위는 이 어댑터 하나뿐 —
feed/html은 실제로 필요해지는 U13(소스 등록 마법사)에서 채운다.

⚠️ 모든 외부 호출은 반드시 url_guard.fetch()를 거친다(CLAUDE.md — 예외 없음). requests를
직접 호출하는 우회 경로를 만들지 말 것.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from xml.etree import ElementTree

from jsonpath_ng.ext import parse as jsonpath_parse

from app.security.url_guard import fetch


def _xml_element_to_dict(elem: ElementTree.Element):
    """XML 엘리먼트를 JSONPath로 훑을 수 있는 dict/list 구조로 변환한다(2026-09-02 —
    과기정통부·방위사업청·발전공기업 등 다수의 data.go.kr API가 `type=json`을 보내도 실제로는
    XML만 돌려주는 걸 실측으로 확인, JSON 전용이던 어댑터에 XML 지원을 추가함).

    같은 태그가 반복되면 리스트로 모은다(예: <items><item/><item/></items> → {"item": [...]}).
    "item"은 data.go.kr 계열 관례상 거의 항상 반복 컨테이너라 **1건이어도 리스트로 강제**한다 —
    안 그러면 결과가 1건일 때 items_path의 `[*]`가 아이템을 못 찾는다.
    """
    children = list(elem)
    if not children:
        return elem.text
    result: dict[str, Any] = {}
    for child in children:
        value = _xml_element_to_dict(child)
        if child.tag == "item" or child.tag in result:
            existing = result.get(child.tag)
            if existing is None:
                result[child.tag] = [value]
            elif isinstance(existing, list):
                existing.append(value)
            else:
                result[child.tag] = [existing, value]
        else:
            result[child.tag] = value
    return result


def _raise_if_error_envelope(payload: Any) -> None:
    """data.go.kr류 API는 요청 포맷(json/xml)과 무관하게 공통 에러 응답 봉투
    (OpenAPI_ServiceResponse.cmmMsgHeader.errMsg)를 쓴다 — 이 구조는 items_path가 가리키는
    정상 응답과 안 겹치므로 그냥 두면 jsonpath가 조용히 빈 리스트를 돌려주고, 이게 "새로
    수집된 공고 없음"과 구분이 안 된다(2026-09-08 실측 — 사전규격정보서비스 일일 요청한도
    초과(LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR)가 조용히 0건 수집으로 처리됨,
    CLAUDE.md S8 "조용한 빈 결과 금지")."""
    if not isinstance(payload, dict):
        return
    gate_header = (payload.get("OpenAPI_ServiceResponse") or {}).get("cmmMsgHeader")
    if gate_header and gate_header.get("errMsg"):
        raise RuntimeError(f"공공데이터포털 API 오류: {gate_header['errMsg']} ({gate_header.get('returnAuthMsg', '')})")

    # 포털 게이트를 통과한 뒤에도(위 cmmMsgHeader 봉투와는 별개로) 각 서비스 자체가
    # response.header.resultCode로 성공/실패를 알린다(2026-09-08, 조달청 3개 서비스 명세서
    # 심층분석으로 확인 — "00"=정상, "03"=데이터 없음(정상, 에러 아님), 그 외 01/02/04~12/
    # 20/22/30~32는 전부 에러). 이것도 안 걸러내면 items_path와 안 겹쳐 조용히 빈 리스트가
    # 된다(위와 같은 CLAUDE.md S8 위반 패턴).
    service_header = (payload.get("response") or {}).get("header")
    if isinstance(service_header, dict):
        result_code = service_header.get("resultCode")
        if result_code is not None and result_code not in ("00", "03"):
            raise RuntimeError(f"공공데이터포털 API 오류(resultCode={result_code}): {service_header.get('resultMsg', '')}")


def _fetch_page(config: dict[str, Any], method: str, endpoint: str, params: dict) -> Any:
    if method == "POST":
        response = fetch(endpoint, method="POST", data=params)
    else:
        response = fetch(endpoint, params=params)
    if config.get("format") == "xml":
        root = ElementTree.fromstring(response.content)
        payload = {root.tag: _xml_element_to_dict(root)}
    else:
        payload = response.json()
    _raise_if_error_envelope(payload)
    return payload


def fetch_openapi_items(config: dict[str, Any], service_key: str | None, *, begin: datetime, end: datetime) -> list[dict]:
    """source_config.config(JSONB) 형태:
    {
      "endpoint": "https://apis.data.go.kr/1230000/ao/BidPublicInfoService/getBidPblancListInfoServc",
      "method": "GET",  # 생략 시 GET. "POST"면 params를 폼 바디로 보낸다(공공데이터포털 API가
                        # 아니라 IRIS처럼 서비스키 없는 내부 JSON 엔드포인트를 그대로 호출할 때 씀 —
                        # advisory INBOX #3, 2026-09-01 직접 확인
      "params": {"inqryDiv": "1", "type": "json", "numOfRows": "100", "pageNo": "1"},
      "format": "xml",  # 생략 시 json. data.go.kr API 다수가 type=json을 보내도 XML만 주는
                        # 경우가 있어(2026-09-02 실측) 필요할 때만 명시 — items_path는 XML도
                        # 동일하게 JSONPath 문법으로 쓴다(변환된 dict/list 구조에 대해 평가됨).
      "date_range_params": {"begin": "inqryBgnDt", "end": "inqryEndDt", "format": "%Y%m%d%H%M"},
      "month_param": "searchDt",  # 선택 — begin/end 쌍이 아니라 "검색년월" 하나만 받는 API용
                        # (예: K-water 3종, 2026-09-03 실측). end 기준 YYYYMM으로 채운다 — 월
                        # 경계를 걸친 수집 공백은 짧은 수집 주기(하루 1회)로는 실질적 영향이 적다.
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

    month_param = config.get("month_param")
    if month_param:
        base_params[month_param] = end.strftime("%Y%m")

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
