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

2026-09-21 — 문서 안에 박힌 이미지(도표·화면 캡처)는 텍스트 레이어에 안 잡혀 지금까지
통째로 유실되고 있었다(의사결정_로그 193번). PDF·hwpx·docx·pptx·xlsx에 대해 본문 추출과
별도로 이미지를 찾아 OCR한 뒤 덧붙인다. HWP(OLE 바이너리)는 이미지가 BinData 스토리지
안에 압축돼 있어 파싱이 훨씬 복잡해 이번 범위에서 제외 — 기존처럼 "<그림>" 자리표시자만
남긴다(향후 과제).
"""

from __future__ import annotations

import io
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import pymupdf as fitz  # 스캔본 PDF를 이미지로 렌더링(OCR 폴백 전용) — "fitz"는 구 패키지명이자
# deprecated import alias(PyMuPDF 공식 권고: pymupdf로 직접 import) — 코드 내부는 익숙한
# 이름(fitz) 그대로 쓰되 실제 import 자체는 신 패키지명으로 한다.
import olefile
import pytesseract
from PIL import Image
from pypdf import PdfReader

_HWPX_PARAGRAPH_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HWP5TXT_TIMEOUT_SEC = 30
_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_SPREADSHEETML_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_WORDPROCESSINGML_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
# 정부 공고 첨부는 거의 전부 한국어라 kor를 우선하되, 도면 치수·모델명 등 영문/숫자가 섞인
# 경우를 위해 eng도 같이 로드한다(2026-09-10, OCR 도입 — 구현스펙 07절 폴백 사슬 마지막 단계).
_OCR_LANG = "kor+eng"
# 스캔본 PDF 페이지를 너무 낮은 해상도로 렌더링하면 작은 글자가 OCR에서 뭉개진다 — 150dpi 기준
# zoom factor(72dpi가 PDF 기본 단위이므로 150/72 ≈ 2.08).
_PDF_OCR_ZOOM = 150 / 72
# 스캔본 PDF는 페이지가 많으면(수십~수백 장) OCR이 매우 오래 걸릴 수 있어 상한을 둔다 — 넘는
# 페이지는 건너뛰고, 몇 페이지까지 처리했는지는 error 없이 method로만 구분한다(잘라도 앞부분
# 텍스트는 실제로 쓸모 있음 — 조용히 버리는 게 아니라 일부라도 확보하는 쪽을 택함).
_PDF_OCR_MAX_PAGES = 20
# 2026-09-21 — 문서 안에 박힌 이미지(도표·화면 캡처)에 담긴 정보가 지금까지 통째로
# 유실되고 있었다(표는 이미 복원하는데 이미지는 텍스트 레이어에 안 잡힘 — "정보는 얻을 수
# 있는 만큼 최대한 수집한다" 원칙 위반). zip 기반 포맷(hwpx/docx/pptx/xlsx)과 PDF에 박힌
# 이미지를 OCR해 본문 뒤에 덧붙인다. 로고·구분선 같은 장식용 그림까지 OCR하면 노이즈만
# 늘어나 최소 크기 미만은 건너뛰고, 문서 하나당 처리량도 상한을 둔다(서버가 ARWS와 자원을
# 공유하는 작은 사양이라 무제한 OCR은 부담). HWP(OLE 바이너리)는 이미지가 BinData 스토리지
# 안에 압축된 형태로 들어있어 훨씬 복잡한 파싱이 필요해 이번 범위에서는 제외했다 — 계속
# 기존처럼 "<그림>" 자리표시자만 남긴다(의사결정_로그 193번, 향후 과제로 기록).
_MIN_EMBEDDED_IMAGE_DIM = 80
_MAX_EMBEDDED_IMAGES_PER_DOC = 15
_EMBEDDED_IMAGE_OCR_HEADER = "<문서 내 이미지 OCR>"


def _ocr_image_bytes(data: bytes) -> str | None:
    """이미지 하나를 OCR한다. 실패(디코딩 불가·엔진 오류)하거나 결과가 비면 None — 문서
    전체 추출을 막으면 안 되므로 예외를 여기서 삼킨다(호출부가 이미지별로 계속 진행)."""
    try:
        image = Image.open(io.BytesIO(data))
        if image.width < _MIN_EMBEDDED_IMAGE_DIM or image.height < _MIN_EMBEDDED_IMAGE_DIM:
            return None
        text = pytesseract.image_to_string(image, lang=_OCR_LANG).strip()
    except Exception:  # noqa: BLE001 — 이미지 하나 실패해도 문서의 나머지 이미지는 계속 처리
        return None
    return text or None


def _extract_zip_embedded_images_ocr(content: bytes, folder_prefix: str) -> str:
    """zip 기반 포맷(hwpx/docx/pptx/xlsx) 공통 — 지정 폴더(BinData/·word/media/ 등) 밑의
    이미지 파일들을 OCR해 하나의 텍스트 블록으로 합친다. 실패해도 빈 문자열만 반환하고
    예외를 올리지 않는다 — 이 결과는 항상 "있으면 덧붙이는" 보조 정보이지 주 추출 성패를
    좌우하면 안 된다."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            image_names = sorted(
                n for n in z.namelist() if n.startswith(folder_prefix) and n.lower().endswith(_IMAGE_EXTENSIONS)
            )[:_MAX_EMBEDDED_IMAGES_PER_DOC]
            parts = [text for name in image_names if (text := _ocr_image_bytes(z.read(name)))]
    except Exception:  # noqa: BLE001
        return ""
    if not parts:
        return ""
    return f"{_EMBEDDED_IMAGE_OCR_HEADER}\n" + "\n\n".join(parts)


def _extract_pdf_embedded_images_ocr(content: bytes) -> str:
    """PDF 페이지 안에 박힌 이미지를 OCR한다(텍스트 레이어 유무와 무관 — 텍스트 레이어가
    있어도 그 옆에 도표·캡처가 별도 이미지로 박혀 있으면 pypdf의 텍스트 추출로는 안 잡힘).
    같은 이미지(반복되는 로고 등)가 여러 페이지에 쓰이면 xref로 중복 판정해 한 번만 OCR."""
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception:  # noqa: BLE001
        return ""
    parts: list[str] = []
    seen_xrefs: set[int] = set()
    try:
        for page in doc:
            if len(seen_xrefs) >= _MAX_EMBEDDED_IMAGES_PER_DOC:
                break
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                try:
                    image_bytes = doc.extract_image(xref)["image"]
                except Exception:  # noqa: BLE001
                    continue
                text = _ocr_image_bytes(image_bytes)
                if text:
                    parts.append(text)
                if len(seen_xrefs) >= _MAX_EMBEDDED_IMAGES_PER_DOC:
                    break
    finally:
        doc.close()
    if not parts:
        return ""
    return f"{_EMBEDDED_IMAGE_OCR_HEADER}\n" + "\n\n".join(parts)


# OLE2 복합 문서 파일(Compound File Binary Format) 매직바이트 — 구버전 HWP5·XLS·DOC가 전부
# 이 컨테이너를 쓴다. 확장자가 .hwpx(zip 기반이어야 정상)인데 실제로는 이 헤더를 가진 경우를
# 잡아내는 데 쓴다(2026-09-11 실측, 나라장터의 확장자 오표기).
_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# ZIP 로컬 파일 헤더 매직바이트 — hwpx/docx/xlsx/pptx 등 OOXML 계열이 전부 이 컨테이너를
# 쓴다. 확장자가 .hwp(OLE 바이너리여야 정상)인데 실제로는 이 헤더를 가진 경우를 잡아내는
# 데 쓴다(2026-09-11 실측 — 위 .hwpx↔OLE 오표기의 반대 방향).
_ZIP_SIGNATURE = b"\x50\x4b\x03\x04"


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
    method: str  # pdf_text / hwpx_xml / hwp5xml / hwp_preview / tesseract_ocr / pdf_ocr
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
        # 텍스트 레이어가 없으면 스캔본일 가능성이 높다 — 바로 실패 처리하지 않고 OCR로 폴백한다
        # (2026-09-10 OCR 도입, 구현스펙 07절 폴백 사슬 마지막 단계).
        return _extract_pdf_ocr(content)
    # 2026-09-21 — 텍스트 레이어가 있어도 페이지에 별도로 박힌 이미지(도표·캡처)는 안 잡힌다
    # (의사결정_로그 193번) — 있으면 덧붙인다.
    image_text = _extract_pdf_embedded_images_ocr(content)
    if image_text:
        text = f"{text}\n\n{image_text}"
    return ExtractResult(text=text, method="pdf_text", ok=True)


def _extract_image_ocr(content: bytes) -> ExtractResult:
    try:
        image = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(image, lang=_OCR_LANG).strip()
    except Exception as exc:  # noqa: BLE001 — 폴백 사슬의 마지막 단계, 실패를 결과로 보고해야 한다
        return ExtractResult(text=None, method="tesseract_ocr", ok=False, error=str(exc))
    if not text:
        return ExtractResult(text=None, method="tesseract_ocr", ok=False, error="OCR 결과가 비어 있음(글자가 없거나 인식 실패)")
    return ExtractResult(text=text, method="tesseract_ocr", ok=True)


def _extract_pdf_ocr(content: bytes) -> ExtractResult:
    """텍스트 레이어가 없는 PDF(스캔본)를 페이지별로 이미지 렌더링 후 OCR한다. 페이지가
    너무 많으면 앞에서부터 _PDF_OCR_MAX_PAGES장까지만 처리 — 일부라도 확보하는 쪽이 통째로
    실패 처리하는 것보다 낫다는 판단(S8 원칙: 조용한 빈 결과 금지, 단 부분 성공은 허용)."""
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        return ExtractResult(text=None, method="pdf_ocr", ok=False, error=str(exc))
    try:
        page_count = doc.page_count
        matrix = fitz.Matrix(_PDF_OCR_ZOOM, _PDF_OCR_ZOOM)
        parts: list[str] = []
        for page in doc[: min(page_count, _PDF_OCR_MAX_PAGES)]:
            pixmap = page.get_pixmap(matrix=matrix)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            page_text = pytesseract.image_to_string(image, lang=_OCR_LANG).strip()
            if page_text:
                parts.append(page_text)
    except Exception as exc:  # noqa: BLE001
        return ExtractResult(text=None, method="pdf_ocr", ok=False, error=str(exc))
    finally:
        doc.close()
    text = "\n\n".join(parts).strip()
    if not text:
        return ExtractResult(text=None, method="pdf_ocr", ok=False, error="스캔본 PDF OCR 결과가 비어 있음(텍스트 레이어도 없고 OCR도 실패)")
    truncated_note = f" (전체 {page_count}페이지 중 앞 {_PDF_OCR_MAX_PAGES}페이지만 처리)" if page_count > _PDF_OCR_MAX_PAGES else ""
    return ExtractResult(text=text + truncated_note, method="pdf_ocr", ok=True)


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
    # 2026-09-21 — 그림(BinData/ 안의 이미지)에 담긴 텍스트는 <hp:t>에 안 잡힌다(의사결정_로그
    # 193번) — 있으면 덧붙인다. 본문 문단이 전혀 없고 이미지만 있는 문서라도 이걸로 살아난다.
    image_text = _extract_zip_embedded_images_ocr(content, "BinData/")
    if image_text:
        text = f"{text}\n\n{image_text}" if text else image_text
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
    # 2026-09-21 — 슬라이드에 박힌 이미지(도표·캡처)도 OCR해 덧붙인다(의사결정_로그 193번).
    image_text = _extract_zip_embedded_images_ocr(content, "ppt/media/")
    if image_text:
        text = f"{text}\n\n{image_text}" if text else image_text
    if not text:
        return ExtractResult(text=None, method="pptx_xml", ok=False, error="추출된 텍스트가 비어 있음")
    return ExtractResult(text=text, method="pptx_xml", ok=True)


def _extract_docx(content: bytes) -> ExtractResult:
    """OOXML(zip+XML) — hwpx·pptx와 같은 구조. word/document.xml의 문단(<w:p>)마다 텍스트
    런(<w:t>)을 이어붙이고, 문단 사이엔 줄바꿈을 넣어 원문 문단 구조를 살린다(2026-09-05,
    고객 소개서 파일이 흔히 .docx라 추가 — 지금까지는 명시적으로 지원하지 않던 형식)."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            if "word/document.xml" not in z.namelist():
                return ExtractResult(text=None, method="docx_xml", ok=False, error="word/document.xml을 찾을 수 없음")
            root = ElementTree.fromstring(z.read("word/document.xml"))
            paragraphs = []
            for p in root.iter(f"{{{_WORDPROCESSINGML_NS}}}p"):
                para_text = "".join(t.text or "" for t in p.iter(f"{{{_WORDPROCESSINGML_NS}}}t"))
                if para_text.strip():
                    paragraphs.append(para_text.strip())
        text = "\n".join(paragraphs).strip()
    except Exception as exc:  # noqa: BLE001
        return ExtractResult(text=None, method="docx_xml", ok=False, error=str(exc))
    # 2026-09-21 — 문서에 박힌 이미지(도표·캡처)도 OCR해 덧붙인다(의사결정_로그 193번).
    image_text = _extract_zip_embedded_images_ocr(content, "word/media/")
    if image_text:
        text = f"{text}\n\n{image_text}" if text else image_text
    if not text:
        return ExtractResult(text=None, method="docx_xml", ok=False, error="추출된 텍스트가 비어 있음")
    return ExtractResult(text=text, method="docx_xml", ok=True)


# 정부 공고 첨부는 오래된 문서일수록 UTF-8이 아니라 한국 레거시 인코딩(CP949/EUC-KR)으로
# 저장된 경우가 흔하다 — 순서대로 시도해 첫 성공을 쓴다(2026-09-11).
_TEXT_ENCODINGS = ("utf-8", "cp949", "euc-kr")


def _extract_txt(content: bytes) -> ExtractResult:
    for encoding in _TEXT_ENCODINGS:
        try:
            text = content.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
        if not text:
            return ExtractResult(text=None, method="plain_text", ok=False, error="파일이 비어 있음")
        return ExtractResult(text=text, method="plain_text", ok=True)
    return ExtractResult(text=None, method="plain_text", ok=False, error="지원하는 인코딩(utf-8/cp949/euc-kr)으로 디코딩 실패")


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
    # 2026-09-21 — 시트에 박힌 이미지(도표·캡처)도 OCR해 덧붙인다(의사결정_로그 193번).
    image_text = _extract_zip_embedded_images_ocr(content, "xl/media/")
    if image_text:
        text = f"{text}\n\n{image_text}" if text else image_text
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
    pptx/xlsx/docx는 hwpx와 같은 OOXML(zip+XML) 구조라 같은 방식으로 직접 파싱한다.
    이미지(png/jpg 등)와 텍스트 레이어 없는 스캔본 PDF는 Tesseract OCR로 처리한다(2026-09-10
    도입 — 구현스펙 07절 폴백 사슬의 마지막 단계. 한국어 문서가 대부분이라 kor+eng 언어팩
    사용, 시스템에 tesseract-ocr·tesseract-ocr-kor 설치 필요).
    """
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _extract_pdf(content)
    if lower.endswith(".hwpx"):
        # 2026-09-11 실측 — 나라장터가 실제로는 구버전 HWP5(OLE 바이너리) 파일에 .hwpx
        # 확장자를 잘못 붙여 주는 사례를 확인(140건, 매직바이트 D0 CF 11 E0로 직접 확인).
        # 확장자만 믿고 zip으로 열면 무조건 "File is not a zip file"로 실패한다 — 내용을
        # 먼저 들여다보고 실제 OLE 구조면 HWP5 경로로 보낸다.
        if content[:len(_OLE_SIGNATURE)] == _OLE_SIGNATURE:
            full = _extract_hwp_full(content)
            return full if full is not None else _extract_hwp_preview(content)
        return _extract_hwpx(content)
    if lower.endswith(".hwp"):
        # 2026-09-11 실측 — 위 .hwpx 오표기의 반대 방향도 실데이터로 확인됨: 실제로는 진짜
        # HWPX(zip, 내용이 "mimetype: application/hwp+zip"로 시작)인데 .hwp 확장자가 붙어
        # 온다. OLE 파서로 열면 "not an OLE2 structured storage file"로 실패한다.
        if content[:len(_ZIP_SIGNATURE)] == _ZIP_SIGNATURE:
            return _extract_hwpx(content)
        full = _extract_hwp_full(content)
        return full if full is not None else _extract_hwp_preview(content)
    if lower.endswith(".pptx"):
        return _extract_pptx(content)
    if lower.endswith((".xlsx", ".xlsm")):
        # .xlsm(매크로 포함 엑셀)은 매크로 스트림만 추가된 것 — 시트/셀 XML 구조는 .xlsx와
        # 완전히 동일해 같은 파서를 그대로 쓸 수 있다(2026-09-11 실측 15건 확인).
        return _extract_xlsx(content)
    if lower.endswith(".docx"):
        return _extract_docx(content)
    if lower.endswith(".txt"):
        return _extract_txt(content)
    if lower.endswith(_IMAGE_EXTENSIONS):
        return _extract_image_ocr(content)
    if lower.endswith(_LEGACY_OFFICE_EXTENSIONS):
        return ExtractResult(text=None, method="unsupported", ok=False, error=f"구버전 오피스 형식(2007 이전)은 아직 지원하지 않음: {filename}")
    return ExtractResult(text=None, method="unsupported", ok=False, error=f"지원하지 않는 형식: {filename}")
