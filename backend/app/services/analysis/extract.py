"""S8 심층분석 — 첨부 규격서 텍스트 추출 폴백 사슬(CLAUDE.md, 설계안 07절 원문 그대로):
HWPX → HWP 전용 파서 → LibreOffice 변환 → PDF → OCR → (전부 실패 시 사용자 붙여넣기, 화면단).

**"조용한 빈 결과 금지"** — 전부 실패하면 무엇을 시도했고 왜 실패했는지 그대로 담아 반환한다.
빈 문자열을 성공으로 위장하지 않는다.

**지금 실제로 동작하는 건 HWPX·PDF·HTML뿐이다.** HWP(구 바이너리 포맷)·LibreOffice 변환·
OCR은 전용 파서나 외부 바이너리(LibreOffice, Tesseract)가 이미지에 설치돼 있어야 하는
인프라 작업이 먼저 필요하다 — 지금은 "시도했으나 미구현"으로 명시하고 실패시킨다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from io import BytesIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# HWPX(OWPML) 본문은 zip 안 Contents/section*.xml에 있고, 텍스트는 <hp:t> 태그 안에 있다.
_HWPX_TEXT_TAG = "{http://www.hancom.co.kr/hwpml/2011/paragraph}t"


@dataclass
class ExtractResult:
    ok: bool
    method: str
    text: str = ""
    error: str | None = None
    attempted: list[str] = field(default_factory=list)


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


def _extract_hwpx(data: bytes) -> tuple[bool, str, str | None]:
    try:
        with ZipFile(BytesIO(data)) as zf:
            section_names = sorted(
                n for n in zf.namelist() if n.startswith("Contents/section") and n.endswith(".xml")
            )
            if not section_names:
                return False, "", "Contents/section*.xml을 찾을 수 없습니다(HWPX 구조가 아닙니다)"
            chunks: list[str] = []
            for name in section_names:
                root = ElementTree.fromstring(zf.read(name))
                chunks.extend(node.text or "" for node in root.iter(_HWPX_TEXT_TAG))
            text = "\n".join(c for c in chunks if c.strip())
            if not text.strip():
                return False, "", "본문 텍스트를 찾지 못했습니다(빈 문서이거나 태그 구조가 다릅니다)"
            return True, text, None
    except (BadZipFile, ElementTree.ParseError) as exc:
        return False, "", f"HWPX 파싱 실패: {exc}"


def _extract_pdf(data: bytes) -> tuple[bool, str, str | None]:
    try:
        reader = PdfReader(BytesIO(data))
        chunks = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(c for c in chunks if c.strip())
        if not text.strip():
            return False, "", "텍스트 레이어가 없습니다(스캔 이미지 PDF로 추정 — OCR 필요)"
        return True, text, None
    except PdfReadError as exc:
        return False, "", f"PDF 파싱 실패: {exc}"
    except Exception as exc:  # noqa: BLE001 — pypdf가 손상 파일에서 다양한 예외를 던짐, 전부 실패로 처리
        return False, "", f"PDF 파싱 실패: {exc}"


def _extract_html(data: bytes) -> tuple[bool, str, str | None]:
    try:
        parser = _TextOnlyHTMLParser()
        parser.feed(data.decode("utf-8", errors="replace"))
        text = parser.text()
        if not text.strip():
            return False, "", "본문 텍스트를 찾지 못했습니다"
        return True, text, None
    except Exception as exc:  # noqa: BLE001
        return False, "", f"HTML 파싱 실패: {exc}"


def _not_implemented(stage: str):
    def _fn(_data: bytes) -> tuple[bool, str, str | None]:
        return False, "", f"{stage} 단계는 아직 구현되지 않았습니다(인프라 작업 필요)"

    return _fn


# kind(analysis_doc.kind: hwp/hwpx/pdf/html)별 시도 순서. CLAUDE.md의 폴백 사슬 순서를
# 그대로 따르되, 이미 형식을 아는 상태이므로 그 형식에 맞는 단계부터 시작한다.
_DISPATCH: dict[str, list[tuple[str, object]]] = {
    "hwpx": [("hwpx", _extract_hwpx)],
    "pdf": [("pdf", _extract_pdf)],
    "html": [("html", _extract_html)],
    "hwp": [
        ("hwp_parser", _not_implemented("HWP 전용 파서")),
        ("libreoffice", _not_implemented("LibreOffice 변환")),
    ],
}


def extract_text(data: bytes, kind: str) -> ExtractResult:
    """kind에 맞는 단계부터 순서대로 시도한다. 전부 실패하면 시도한 단계 목록과 마지막
    오류를 그대로 반환한다 — analysis_doc.extract_method/extract_ok/error에 그대로 대응.
    """
    stages = _DISPATCH.get(kind, [])
    attempted: list[str] = []
    last_error: str | None = None
    for method, fn in stages:
        attempted.append(method)
        ok, text, error = fn(data)
        if ok:
            return ExtractResult(ok=True, method=method, text=text, attempted=attempted)
        last_error = error

    return ExtractResult(
        ok=False,
        method=attempted[-1] if attempted else "unsupported",
        error=last_error or f"지원하지 않는 문서 형식입니다: {kind}",
        attempted=attempted,
    )
