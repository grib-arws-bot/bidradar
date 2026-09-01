"""S8 문서 텍스트 추출 폴백 사슬 검증 — "조용한 빈 결과 금지"(CLAUDE.md)."""

from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from pypdf import PdfWriter

from app.services.analysis.extract import extract_text

_HWPX_SECTION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p><hp:run><hp:t>과업 목표: 지능형 CCTV 통합관제시스템 구축</hp:t></hp:run></hp:p>
  <hp:p><hp:run><hp:t>해상도 400만화소 이상</hp:t></hp:run></hp:p>
</hp:sec>
"""


def _build_hwpx_bytes() -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("Contents/section0.xml", _HWPX_SECTION_XML)
    return buf.getvalue()


def test_extract_hwpx_success():
    result = extract_text(_build_hwpx_bytes(), "hwpx")
    assert result.ok is True
    assert result.method == "hwpx"
    assert "지능형 CCTV" in result.text
    assert "400만화소" in result.text


def test_extract_hwpx_malformed_zip_fails_loudly():
    result = extract_text(b"this is not a zip file", "hwpx")
    assert result.ok is False
    assert result.error is not None
    assert result.attempted == ["hwpx"]


def test_extract_pdf_garbage_bytes_fails_loudly():
    result = extract_text(b"%PDF-not-a-real-pdf", "pdf")
    assert result.ok is False
    assert result.error is not None


def test_extract_pdf_blank_page_has_no_text_layer():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)

    result = extract_text(buf.getvalue(), "pdf")
    assert result.ok is False
    assert "텍스트 레이어" in result.error


def test_extract_html_success_and_strips_script():
    html = b"<html><body><p>\xec\x95\x88\xeb\x85\x95\xed\x95\x98\xec\x84\xb8\xec\x9a\x94 \xed\x85\x8c\xec\x8a\xa4\xed\x8a\xb8</p><script>ignored()</script></body></html>"
    result = extract_text(html, "html")
    assert result.ok is True
    assert "테스트" in result.text
    assert "ignored" not in result.text


def test_extract_html_empty_body_fails():
    result = extract_text(b"<html><body></body></html>", "html")
    assert result.ok is False


def test_extract_hwp_is_explicitly_not_implemented_not_silent():
    result = extract_text(b"legacy hwp binary content", "hwp")
    assert result.ok is False
    assert result.attempted == ["hwp_parser", "libreoffice"]
    assert "구현되지 않았습니다" in result.error


def test_extract_unsupported_kind_fails_with_clear_message():
    result = extract_text(b"...", "docx")
    assert result.ok is False
    assert "지원하지 않는 문서 형식" in result.error
    assert result.attempted == []
