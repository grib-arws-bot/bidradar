"""html 어댑터(app/collector/adapters/html.py) 검증 — 국가철도공단(KR) 실제 페이지 구조를
단순화한 고정 HTML로 파싱·페이지네이션·상세 URL 조립을 확인한다. 실제 네트워크 호출 없음
(app.collector.adapters.html.fetch를 몽키패치)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://bidradar:devpassword@127.0.0.1:15432/bidradar")

from app.collector.adapters.html import fetch_html_items

_CONFIG = {
    "endpoint": "https://ebid.kr.or.kr/bid/anc/bidAncList.do",
    "params": {"menuNo": "14000"},
    "date_range_params": {"begin": "fromDate", "end": "endDate", "format": "%Y-%m-%d"},
    "pagination": {"page_param": "pageIndex", "max_pages": 10},
    "table_class": "tbl01",
    "columns": ["biz_type_raw", "notice_no", "title", "est_price", "open_dt", "close_dt", "status"],
    "detail_link_column_index": 2,
    "detail_endpoint": "https://ebid.kr.or.kr/bid/anc/bidAncDetail.do",
    "detail_param_names": [
        "gyErBeonho", "crSangtae", "ggDrIrja", "ggNyeondo", "ggIrBeonho",
        "ygGeumaeg", "ggChasu", "cjbcDrMyeong", "irBeonho", "ggGubun",
    ],
}


def _page_html(rows: str) -> str:
    # 실제 사이트의 헤더 행(<th>, 셀 수 0)도 함께 넣어 필터링을 같이 검증한다.
    return f"""
    <table class="tbl01" summary="입찰공고 목록">
        <thead><tr><th>구분</th><th>공고번호</th><th>공고명</th><th>금액</th><th>공고게시일</th><th>개찰예정일</th><th>처리상태</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>
    """


_ROW_1 = """
<tr>
    <td>용역</td>
    <td>2026-02-000513-00</td>
    <td class="t_left"><a href="javascript:detail('2000012933','04','2026-09-10 00:00:00.0','2026','000513','57420000','00','','','02')">
        호남선 노안교 등 7개소 내진성능보강공사 건설폐기물 처리용역
    </a></td>
    <td class="t_right">57,420,000</td>
    <td>2026-09-11</td>
    <td>2026-09-18</td>
    <td>공고게시</td>
</tr>
"""

_ROW_2 = """
<tr>
    <td>구매</td>
    <td>2026-03-000219-00</td>
    <td class="t_left"><a href="javascript:detail('1000012732','04','2026-09-11 00:00:00.0','2026','000219','3828540000','00','','','03')">
        CCTV 영상관제 통합플랫폼 장비 구매
    </a></td>
    <td class="t_right">3,828,540,000</td>
    <td>2026-09-11</td>
    <td>2026-09-18</td>
    <td>공고게시</td>
</tr>
"""


def test_fetch_html_items_parses_rows_and_builds_detail_url(monkeypatch):
    response = mock.Mock()
    response.text = _page_html(_ROW_1 + _ROW_2)
    mock_fetch = mock.Mock(side_effect=[response, mock.Mock(text=_page_html(""))])
    monkeypatch.setattr("app.collector.adapters.html.fetch", mock_fetch)

    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    items = fetch_html_items(_CONFIG, begin=now, end=now)

    assert len(items) == 2
    assert items[0]["title"] == "호남선 노안교 등 7개소 내진성능보강공사 건설폐기물 처리용역"
    assert items[0]["notice_no"] == "2026-02-000513-00"
    assert items[0]["biz_type_raw"] == "용역"
    assert items[0]["est_price"] == "57,420,000"
    assert items[0]["open_dt"] == "2026-09-11"
    assert items[0]["close_dt"] == "2026-09-18"
    assert items[0]["url"] == (
        "https://ebid.kr.or.kr/bid/anc/bidAncDetail.do?"
        "gyErBeonho=2000012933&crSangtae=04&ggDrIrja=2026-09-10+00%3A00%3A00.0&ggNyeondo=2026"
        "&ggIrBeonho=000513&ygGeumaeg=57420000&ggChasu=00&cjbcDrMyeong=&irBeonho=&ggGubun=02"
    )
    assert items[1]["title"] == "CCTV 영상관제 통합플랫폼 장비 구매"

    # 페이지네이션·날짜범위 파라미터가 실제로 전달됐는지도 같이 확인
    first_call_params = mock_fetch.call_args_list[0].kwargs["params"]
    assert first_call_params["pageIndex"] == "1"
    assert first_call_params["fromDate"] == "2026-09-13"
    assert first_call_params["endDate"] == "2026-09-13"
    assert first_call_params["menuNo"] == "14000"


def test_fetch_html_items_stops_on_empty_page(monkeypatch):
    page1 = mock.Mock(text=_page_html(_ROW_1))
    page2 = mock.Mock(text=_page_html(""))  # 빈 페이지 — 더 안 감
    mock_fetch = mock.Mock(side_effect=[page1, page2])
    monkeypatch.setattr("app.collector.adapters.html.fetch", mock_fetch)

    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    items = fetch_html_items(_CONFIG, begin=now, end=now)

    assert len(items) == 1
    assert mock_fetch.call_count == 2  # 2페이지 요청 후(빈 결과) 3페이지는 요청 안 함


def test_fetch_html_items_ignores_header_row_with_mismatched_cell_count(monkeypatch):
    # thead의 <th> 행은 <td> 파서가 안 잡으므로 셀 0개 — 결과에 안 섞여야 함
    response = mock.Mock(text=_page_html(_ROW_1))
    mock_fetch = mock.Mock(side_effect=[response, mock.Mock(text=_page_html(""))])
    monkeypatch.setattr("app.collector.adapters.html.fetch", mock_fetch)

    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    items = fetch_html_items(_CONFIG, begin=now, end=now)
    assert len(items) == 1
