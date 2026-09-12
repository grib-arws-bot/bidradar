"""HTML에서 본문 텍스트만 뽑아내는 공용 유틸 — app/services/analysis/extract.py(S8 규격서
추출)와 app/services/customer_profile.py(고객 참고 URL 수집)가 함께 쓴다."""

from __future__ import annotations

from html.parser import HTMLParser


class _TextAndLinksHTMLParser(HTMLParser):
    """본문 텍스트뿐 아니라 <a href> 링크도 함께 모은다 — customer_profile.py의 참고 URL
    같은 도메인 재귀 크롤링(2026-09-11)에 쓴다. 텍스트만 필요하면 html_to_text()만 쓰면 됨."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = False
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001 — stdlib 시그니처 그대로
        if tag in ("script", "style"):
            self._skip = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def html_to_text(html: str) -> str:
    parser = _TextAndLinksHTMLParser()
    parser.feed(html)
    return parser.text()


def extract_text_and_links(html: str) -> tuple[str, list[str]]:
    parser = _TextAndLinksHTMLParser()
    parser.feed(html)
    return parser.text(), parser.links
