"""S8 A1 문서 추출(파일럿, 2026-09-03) — 구현스펙 07절 "A1 문서 추출 — 폴백 사슬" 중
지금 실제로 구현하는 부분만: PDF·HWPX 전문 추출 + HWP(구버전) 미리보기.

Phase 0 실측 결과(같은 날 조사) — PDF는 텍스트 레이어 추출이 바로 성공, HWPX는 zip 안의
Contents/section*.xml을 파싱하면 전문이 나온다(둘 다 폴백 없이 1단계 성공). 구버전 HWP(OLE
바이너리)는 PrvText 스트림에서 "미리보기"(~1000자, 문서 전체 아님)만 뽑을 수 있고, 본문
전체를 뽑으려면 HWP5 레코드 파서나 LibreOffice 변환이 필요하다 — 이번 파일럿 범위 밖이라
미리보기만 제공하고 extract_method로 그 사실을 명시한다(조용히 빈/불완전 결과로 진행 금지).

LibreOffice·OCR 폴백은 다음 단계(HWP 전문 추출이 실제로 필요해지면) 추가한다.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

import olefile
from pypdf import PdfReader

_HWPX_PARAGRAPH_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


@dataclass
class ExtractResult:
    text: str | None
    method: str  # pdf_text / hwpx_xml / hwp_preview
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
                    if t_elem.text:
                        parts.append(t_elem.text)
        text = "\n".join(parts).strip()
    except Exception as exc:  # noqa: BLE001
        return ExtractResult(text=None, method="hwpx_xml", ok=False, error=str(exc))
    if not text:
        return ExtractResult(text=None, method="hwpx_xml", ok=False, error="추출된 텍스트가 비어 있음")
    return ExtractResult(text=text, method="hwpx_xml", ok=True)


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


def extract_document(filename: str, content: bytes) -> ExtractResult:
    """확장자로 추출 방법을 고른다. 지원하지 않는 형식(zip·odt 등)은 ok=False로 명시 보고 —
    조용히 건너뛰지 않는다(S8 원칙: 조용한 빈 결과 금지).
    """
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _extract_pdf(content)
    if lower.endswith(".hwpx"):
        return _extract_hwpx(content)
    if lower.endswith(".hwp"):
        return _extract_hwp_preview(content)
    return ExtractResult(text=None, method="unsupported", ok=False, error=f"지원하지 않는 형식: {filename}")
