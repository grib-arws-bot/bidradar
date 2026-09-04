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


def _extract_hwp_full(content: bytes) -> ExtractResult | None:
    """pyhwp(hwp5txt)로 HWP5 전문 추출. 바이너리가 없거나 실패하면 None — 호출부가
    PrvText 미리보기로 폴백한다."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "input.hwp"
            src.write_bytes(content)
            result = subprocess.run(
                ["hwp5txt", str(src)], capture_output=True, timeout=_HWP5TXT_TIMEOUT_SEC
            )
            if result.returncode != 0:
                return None
            text = result.stdout.decode("utf-8", errors="replace").strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not text:
        return None
    return ExtractResult(text=text, method="hwp5txt", ok=True)


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

    HWP는 pyhwp(hwp5txt) 전문 추출 우선 → 실패 시 PrvText 미리보기(~1000자)로 폴백.
    """
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _extract_pdf(content)
    if lower.endswith(".hwpx"):
        return _extract_hwpx(content)
    if lower.endswith(".hwp"):
        full = _extract_hwp_full(content)
        return full if full is not None else _extract_hwp_preview(content)
    return ExtractResult(text=None, method="unsupported", ok=False, error=f"지원하지 않는 형식: {filename}")
