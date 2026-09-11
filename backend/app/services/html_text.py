"""HTML에서 본문 텍스트만 뽑아내는 공용 유틸 — app/services/analysis/extract.py(S8 규격서
추출)와 app/services/customer_profile.py(고객 참고 URL 수집)가 함께 쓴다."""

from __future__ import annotations

from html.parser import HTMLParser


class _TextOnlyHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001 — stdlib 시그니처 그대로
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def html_to_text(html: str) -> str:
    parser = _TextOnlyHTMLParser()
    parser.feed(html)
    return parser.text()
