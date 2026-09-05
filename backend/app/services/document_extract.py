"""S8 A1 문서 추출 — 구현스펙 07절 "A1 문서 추출 — 폴백 사슬" 중 PDF·HWPX·HWP 전문 추출 +
미리보기 최종 폴백.

Phase 0 실측 결과(2026-09-03) — PDF는 텍스트 레이어 추출이 바로 성공, HWPX는 zip 안의
Contents/section*.xml을 파싱하면 전문이 나온다.

2026-09-04 — HWP(구버전 OLE 바이너리, 실제로는 대부분 HWP5) 전문 추출을 처음엔 LibreOffice
headless 변환으로 시도했으나, 실제 나라장터 첨부문서로 검증한 결과 이 프로젝트가 쓰는
LibreOffice 7.4 빌드엔 "Hangul WP 97"(writer_MIZI_Hwp_97, 구버전 HWP 2~3.x 전용) 필터만
등록돼 있고 현재 정부 사이트가 쓰는 HWP5는 아예 못 연다("source file could not be loaded",
HWPX도 동일 — LibreOffice가 이 배포판에서 두 형식 모두 못 읾을 확인). 대신 실제 HWP5 바이너리
레코드를 파싱하는 `pyhwp`(hwp5txt CLI)로 교체 — 나라장터 실제 첨부문서로 전문 추출 성공을
확인함. pyhwp가 없거나 실패하는 환경에서는 PrvText 미리보기(~1000자)로 폴백한다 — 어느
단계에서 성공했는지 extract_method에 항상 남긴다(S8 원칙: 조용한 빈 결과 금지).
"""

from __future__ import annotations

import io
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import olefile
from pypdf import PdfReader

_HWPX_PARAGRAPH_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HWP5TXT_TIMEOUT_SEC = 30
_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_SPREADSHEETML_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _flatten_hwpx_text(t_elem: ElementTree.Element) -> str:
    """<hp:t> 안에 <hp:lineBreak/>·<hp:tab/> 같은 인라인 태그가 섞이면 ElementTree가 텍스트를
    text/tail로 쪼갠다 — .text만 읽으면 태그 뒤 내용이 통째로 사라진다(2026-09-05, 실제 규격서
    표에서 발견: "100분의 75 이하" 같은 핵심 수치가 줄바꿈 태그 뒤에 있어 유실되고 있었음).
    태그는 공백으로 치환해 이어붙인다."""
    fragments = [t_elem.text or ""]
    for child in t_elem:
        fragments.append(" ")
        fragments.append(child.tail or "")
    return " ".join("".join(fragments).split())


@dataclass
class ExtractResult:
    text: str | None
    method: str  # pdf_text / hwpx_xml / hwp5txt / hwp_preview
    ok: bool
    error: str | None = None


def _extract_pdf(content: bytes) -> ExtractResult:
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
    except Exception as exc:  # noqa: BLE001 — 폴백 사슬의 한 단계, 실패를 결과로 보고해야 한다
        return ExtractResult(text=None, method="pdf_text", ok=False, error=str(exc))
    if not text:
        return ExtractResult(text=None, method="pdf_text", ok=False, error="텍스트 레이어가 비어 있음(스캔본 가능성)")
    return ExtractResult(text=text, method="pdf_text", ok=True)


def _extract_hwpx(content: bytes) -> ExtractResult:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            section_names = sorted(n for n in z.namelist() if n.startswith("Contents/section") and n.endswith(".xml"))
            if not section_names:
                return ExtractResult(text=None, method="hwpx_xml", ok=False, error="Contents/section*.xml을 찾을 수 없음")
            parts: list[str] = []
            for name in section_names:
                root = ElementTree.fromstring(z.read(name))
                for t_elem in root.iter(f"{{{_HWPX_PARAGRAPH_NS}}}t"):
                    text = _flatten_hwpx_text(t_elem)
                    if text:
                        parts.append(text)
        text = "\n".join(parts).strip()
    except Exception as exc:  # noqa: BLE001
        return ExtractResult(text=None, method="hwpx_xml", ok=False, error=str(exc))
    if not text:
        return ExtractResult(text=None, method="hwpx_xml", ok=False, error="추출된 텍스트가 비어 있음")
    return ExtractResult(text=text, method="hwpx_xml", ok=True)


def _extract_pptx(content: bytes) -> ExtractResult:
    """OOXML(zip+XML) — hwpx와 같은 구조. 슬라이드별 텍스트 상자(<a:t>)만 순서대로 이어붙인다."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            slide_names = sorted(
                n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            )
            if not slide_names:
                return ExtractResult(text=None, method="pptx_xml", ok=False, error="ppt/slides/slide*.xml을 찾을 수 없음")
            parts: list[str] = []
            for name in slide_names:
                root = ElementTree.fromstring(z.read(name))
                slide_text = " ".join(t.text for t in root.iter(f"{{{_DRAWINGML_NS}}}t") if t.text)
                if slide_text:
                    parts.append(slide_text)
        text = "\n".join(parts).strip()
    except Exception as exc:  # noqa: BLE001
        return ExtractResult(text=None, method="pptx_xml", ok=False, error=str(exc))
    if not text:
        return ExtractResult(text=None, method="pptx_xml", ok=False, error="추출된 텍스트가 비어 있음")
    return ExtractResult(text=text, method="pptx_xml", ok=True)


def _extract_xlsx(content: bytes) -> ExtractResult:
    """OOXML(zip+XML) — 공유 문자열(xl/sharedStrings.xml)과 시트 내 인라인 문자열만 모은다.
    표 구조(행/열, 셀 좌표)는 보존하지 않는 단순 텍스트 나열이다 — 서식·규격서처럼 셀에 담긴
    설명 텍스트를 찾는 용도로는 충분하지만, 숫자만 있는 표는 맥락 없이 값만 나열될 수 있다."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            parts: list[str] = []
            if "xl/sharedStrings.xml" in z.namelist():
                root = ElementTree.fromstring(z.read("xl/sharedStrings.xml"))
                for si in root.iter(f"{{{_SPREADSHEETML_NS}}}si"):
                    si_text = "".join(t.text or "" for t in si.iter(f"{{{_SPREADSHEETML_NS}}}t"))
                    if si_text.strip():
                        parts.append(si_text.strip())
            sheet_names = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            for name in sheet_names:
                root = ElementTree.fromstring(z.read(name))
                for is_elem in root.iter(f"{{{_SPREADSHEETML_NS}}}is"):
                    is_text = "".join(t.text or "" for t in is_elem.iter(f"{{{_SPREADSHEETML_NS}}}t"))
                    if is_text.strip():
                        parts.append(is_text.strip())
        text = "\n".join(parts).strip()
    except Exception as exc:  # noqa: BLE001
        return ExtractResult(text=None, method="xlsx_xml", ok=False, error=str(exc))
    if not text:
        return ExtractResult(text=None, method="xlsx_xml", ok=False, error="추출된 텍스트가 비어 있음")
    return ExtractResult(text=text, method="xlsx_xml", ok=True)


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _render_hwp_table(table_elem: ElementTree.Element) -> str:
    """<표> 자리표시자 대신 실제 셀 내용을 표로 풀어낸다(2026-09-05, 실제 규격서에서 발견 —
    "세부사업(내역사업)"·문의처 담당자 등 핵심 정보가 표에만 있는 경우가 흔해, 자리표시자만
    남기면 그 정보가 통째로 사라짐). 행은 줄바꿈, 셀은 " | "로 구분."""
    body = table_elem.find("TableBody")
    if body is None:
        return "\n<표>\n"
    rows = []
    for row in body.findall("TableRow"):
        cells = []
        for cell in row.findall("TableCell"):
            cell_text = "".join(_walk_hwp_element(child) for child in cell)
            cell_text = " ".join(cell_text.split())  # 셀 안 개행을 공백으로(표 한 줄에 담기 위해)
            cells.append(cell_text)
        if any(cells):
            rows.append(" | ".join(cells))
    if not rows:
        return "\n<표>\n"
    return "\n<표>\n" + "\n".join(rows) + "\n"


def _walk_hwp_element(elem: ElementTree.Element) -> str:
    """hwp5proc xml 결과를 pyhwp의 plaintext.xsl과 같은 규칙(Paragraph=줄바꿈,
    ControlChar=무시)으로 걷되, TableControl만 자리표시자가 아니라 실제 내용을 채운다."""
    tag = _local_tag(elem.tag)
    if tag == "Text":
        return elem.text or ""
    if tag == "ControlChar":
        return ""
    if tag == "TableControl":
        return _render_hwp_table(elem)
    if tag == "GShapeObjectControl":
        return "\n<그림>\n"
    text = "".join(_walk_hwp_element(child) for child in elem)
    if tag == "Paragraph":
        text += "\n"
    return text


def _extract_hwp_full(content: bytes) -> ExtractResult | None:
    """pyhwp(hwp5proc xml)로 HWP5 전체 XML 모델을 뽑아 직접 걷는다 — 바이너리가 없거나
    실패하면 None(호출부가 PrvText 미리보기로 폴백).

    2026-09-05 — 기존엔 `hwp5txt` CLI를 그대로 썼는데, 이 CLI가 쓰는 plaintext.xsl이 표
    (TableControl)를 안의 내용은 다 버리고 "<표>" 문자만 남기도록 만들어져 있었다(pyhwp
    자체 한계, 실제 XML 모델엔 셀 내용이 완전히 들어있음을 hwp5proc xml로 확인). 규격서의
    "세부사업(내역사업)"·문의처 담당자·평가항목 배점 등 핵심 정보가 표에만 있는 경우가
    많아 원문 XML을 직접 걸어 표 내용을 복원한다."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "input.hwp"
            dest = Path(tmpdir) / "output.xml"
            src.write_bytes(content)
            result = subprocess.run(
                ["hwp5proc", "xml", str(src), "--output", str(dest)],
                capture_output=True, timeout=_HWP5TXT_TIMEOUT_SEC,
            )
            if result.returncode != 0 or not dest.exists():
                return None
            root = ElementTree.parse(dest).getroot()
            bodytext = root.find("BodyText")
            if bodytext is None:
                return None
            text = "".join(_walk_hwp_element(child) for child in bodytext).strip()
    except (OSError, subprocess.SubprocessError, ElementTree.ParseError):
        return None
    if not text:
        return None
    return ExtractResult(text=text, method="hwp5xml", ok=True)


def _extract_hwp_preview(content: bytes) -> ExtractResult:
    try:
        with olefile.OleFileIO(io.BytesIO(content)) as ole:
            if not ole.exists("PrvText"):
                return ExtractResult(text=None, method="hwp_preview", ok=False, error="PrvText 스트림이 없음")
            raw = ole.openstream("PrvText").read()
        text = raw.decode("utf-16-le", errors="ignore").strip()
    except Exception as exc:  # noqa: BLE001
        return ExtractResult(text=None, method="hwp_preview", ok=False, error=str(exc))
    if not text:
        return ExtractResult(text=None, method="hwp_preview", ok=False, error="미리보기가 비어 있음")
    return ExtractResult(text=text, method="hwp_preview", ok=True)


_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff")
_LEGACY_OFFICE_EXTENSIONS = (".doc", ".ppt", ".xls")  # OLE 바이너리(2007 이전) — 별도 파서 미도입


def extract_document(filename: str, content: bytes) -> ExtractResult:
    """확장자로 추출 방법을 고른다. 지원하지 않는 형식은 ok=False로 명시 보고 — 조용히
    건너뛰지 않는다(S8 원칙: 조용한 빈 결과 금지).

    HWP는 pyhwp(hwp5txt) 전문 추출 우선 → 실패 시 PrvText 미리보기(~1000자)로 폴백.
    pptx/xlsx는 hwpx와 같은 OOXML(zip+XML) 구조라 같은 방식으로 직접 파싱한다.
    이미지(png/jpg 등)는 OCR 파이프라인이 아직 없어(구현스펙 07절 폴백 사슬의 마지막 단계,
    미구현) 지원하지 않음을 명시 보고한다 — 나중에 OCR을 붙이면 이 분기만 바꾸면 됨.
    """
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _extract_pdf(content)
    if lower.endswith(".hwpx"):
        return _extract_hwpx(content)
    if lower.endswith(".hwp"):
        full = _extract_hwp_full(content)
        return full if full is not None else _extract_hwp_preview(content)
    if lower.endswith(".pptx"):
        return _extract_pptx(content)
    if lower.endswith(".xlsx"):
        return _extract_xlsx(content)
    if lower.endswith(_IMAGE_EXTENSIONS):
        return ExtractResult(text=None, method="unsupported", ok=False, error=f"이미지 파일은 OCR 미구현으로 아직 지원하지 않음: {filename}")
    if lower.endswith(_LEGACY_OFFICE_EXTENSIONS):
        return ExtractResult(text=None, method="unsupported", ok=False, error=f"구버전 오피스 형식(2007 이전)은 아직 지원하지 않음: {filename}")
    return ExtractResult(text=None, method="unsupported", ok=False, error=f"지원하지 않는 형식: {filename}")
