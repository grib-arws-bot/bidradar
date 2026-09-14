"""html 어댑터 — 공공데이터포털 API가 없어 자체 전자조달 사이트를 직접 스크레이핑해야 하는
소스용(설계안 04-1 "openapi/feed/html" 중 마지막 타입, 2026-09-13 국가철도공단(KR)으로 처음
도입). openapi 어댑터와 달리 소스 전용 코드가 불가피하다 — g2b/IRIS급 JSON API처럼 필드가
표준화돼 있지 않고, 사이트마다 목록 페이지 구조·페이지네이션 방식이 전부 다르기 때문이다.

⚠️ 모든 외부 호출은 반드시 url_guard.fetch()를 거친다(CLAUDE.md — 예외 없음).

국가철도공단 KR전자조달시스템(ebid.kr.or.kr) 실측 확인(2026-09-13):
- 목록: GET /bid/anc/bidAncList.do?menuNo=14000&pageIndex=N&fromDate=YYYY-MM-DD&endDate=YYYY-MM-DD
  robots.txt 전면허용, 로그인 불필요, 정적 서버렌더링(curl로 그대로 보임).
- 표(class="tbl01") 각 행 7개 셀: 공고구분/공고번호/공고명(+상세 파라미터가 담긴 onclick)/
  금액/공고게시일/개찰예정일/처리상태.
- 상세 페이지 파라미터는 <a href="javascript:detail(a,b,...)">에 그대로 노출돼 있어 별도 요청
  없이 목록 HTML만으로 상세 URL을 조립할 수 있다(GET으로도 동작 확인됨).
- 이용약관(/html/clause.html)은 전자입찰 참가자 대상 조항뿐, 크롤링·재배포 금지 조항 없음.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlencode

from app.security.url_guard import fetch

# javascript:<함수명>('a','b',...) 형태에서 인자 목록을 뽑는다. 함수명은 사이트마다 다르다
# (국가철도공단은 detail(...), 한국가스공사는 viewBid(...), 2026-09-14 실측) — config의
# "detail_js_function"으로 지정, 기본값은 기존 국가철도공단 설정과의 호환을 위해 "detail".
# 인자 안 홑따옴표는 \' 로 이스케이프된다고 가정(다른 국가기관 전자조달 사이트 관례) —
# 지금까지 실측 데이터에는 없었지만 안전하게 처리.
_ARG_RE = re.compile(r"'((?:[^'\\]|\\.)*)'")


class _NoticeTableParser(HTMLParser):
    """공고 목록 표(class="tbl01") 안의 <tr>을 셀 단위(텍스트+첫 링크 href)로 뽑는다.
    헤더 행은 <th>라 셀 수가 0으로 걸러진다."""

    def __init__(self, *, table_class: str) -> None:
        super().__init__()
        self._table_class = table_class
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._row_cells: list[dict[str, Any]] = []
        self._cell_text: list[str] = []
        self._current_href: str | None = None
        self.rows: list[list[dict[str, Any]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        if tag == "table" and (attrs_d.get("class") or "") == self._table_class:
            self._in_table = True
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._row_cells = []
        elif self._in_row and tag == "td":
            self._in_cell = True
            self._cell_text = []
            self._current_href = None
        elif self._in_cell and tag == "a" and attrs_d.get("href"):
            self._current_href = attrs_d["href"]

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._in_table:
            self._in_table = False
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if self._row_cells:
                self.rows.append(self._row_cells)
        elif tag == "td" and self._in_cell:
            self._row_cells.append({"text": "".join(self._cell_text).strip(), "href": self._current_href})
            self._in_cell = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_text.append(data)


def _parse_detail_args(href: str | None, *, js_function: str) -> list[str] | None:
    if not href:
        return None
    match = re.search(re.escape(js_function) + r"\((.*)\)", href)
    if not match:
        return None
    return [a.replace("\\'", "'") for a in _ARG_RE.findall(match.group(1))]


def _row_to_item(cells: list[dict[str, Any]], config: dict[str, Any]) -> dict | None:
    columns = config["columns"]  # 예: ["biz_type_raw","notice_no","title","est_price","open_dt","close_dt","status"]
    if len(cells) != len(columns):
        return None
    item: dict[str, Any] = {name: cells[i]["text"] for i, name in enumerate(columns)}

    title_col_index = config.get("detail_link_column_index")
    detail_endpoint = config.get("detail_endpoint")
    detail_param_names = config.get("detail_param_names")
    if title_col_index is not None and detail_endpoint and detail_param_names:
        js_function = config.get("detail_js_function", "detail")
        args = _parse_detail_args(cells[title_col_index]["href"], js_function=js_function)
        if args and len(args) >= len(detail_param_names):
            item["url"] = f"{detail_endpoint}?{urlencode(dict(zip(detail_param_names, args)))}"
    return item


def fetch_html_items(config: dict[str, Any], service_key: str | None = None, *, begin, end) -> list[dict]:
    """source_config.config(JSONB) 형태:
    {
      "endpoint": "https://ebid.kr.or.kr/bid/anc/bidAncList.do",
      "params": {"menuNo": "14000"},
      "date_range_params": {"begin": "fromDate", "end": "endDate", "format": "%Y-%m-%d"},
      "pagination": {"page_param": "pageIndex", "max_pages": 60},
      "table_class": "tbl01",
      "columns": ["biz_type_raw", "notice_no", "title", "est_price", "open_dt", "close_dt", "status"],
      "detail_link_column_index": 2,
      "detail_endpoint": "https://ebid.kr.or.kr/bid/anc/bidAncDetail.do",
      "detail_param_names": ["gyErBeonho","crSangtae","ggDrIrja","ggNyeondo","ggIrBeonho","ygGeumaeg","ggChasu","cjbcDrMyeong","irBeonho","ggGubun"]
    }

    service_key는 이 어댑터에선 안 쓴다(openapi 어댑터와 호출 시그니처를 맞추기 위해서만 받음).
    페이지는 빈 결과가 나올 때까지 순차 조회한다(총 페이지수를 안 믿고 안전하게 — openapi
    어댑터의 pagination_stops_on_empty_page와 같은 방식)."""
    endpoint = config["endpoint"]
    base_params = dict(config.get("params", {}))

    date_range = config.get("date_range_params")
    if date_range:
        fmt = date_range.get("format", "%Y-%m-%d")
        base_params[date_range["begin"]] = begin.strftime(fmt)
        base_params[date_range["end"]] = end.strftime(fmt)

    pagination = config.get("pagination", {})
    page_param = pagination.get("page_param", "pageIndex")
    max_pages = pagination.get("max_pages", 50)
    table_class = config.get("table_class", "tbl01")

    all_items: list[dict] = []
    page = 1
    while page <= max_pages:
        params = dict(base_params)
        params[page_param] = str(page)
        response = fetch(endpoint, params=params)
        parser = _NoticeTableParser(table_class=table_class)
        parser.feed(response.text)
        if not parser.rows:
            break
        for cells in parser.rows:
            item = _row_to_item(cells, config)
            if item:
                all_items.append(item)
        page += 1

    return all_items
