"""S8 A1 문서 추출 파일럿(2026-09-03) — app/services/document_extract.py 검증.

PDF·HWP(OLE)는 유효한 바이너리를 손으로 만들기 까다로워(특히 pypdf는 xref 정합성에
엄격하고, olefile은 쓰기를 지원 안 함) 실제 라이브러리 호출부를 모킹해 우리 쪽 래핑
로직(빈 텍스트/예외 → ok=False, 성공 시 텍스트 반환)만 검증한다. HWPX는 zip+xml이라
진짜 파일을 그대로 만들어 검증한다 — 이쪽은 모킹할 이유가 없다.
"""

from __future__ import annotations

import io
import zipfile
from unittest import mock

from app.services.document_extract import extract_document

_HWPX_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _make_hwpx(paragraphs: list[str]) -> bytes:
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?><hs:sec xmlns:hs="ns" xmlns:hp="{_HWPX_NS}">'
        + "".join(f"<hp:p><hp:run><hp:t>{p}</hp:t></hp:run></hp:p>" for p in paragraphs)
        + "</hs:sec>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", xml)
    return buf.getvalue()


def test_extract_hwpx_joins_paragraph_text():
    content = _make_hwpx(["첫 문단입니다.", "둘째 문단입니다."])
    result = extract_document("공고문.hwpx", content)
    assert result.ok is True
    assert result.method == "hwpx_xml"
    assert "첫 문단입니다." in result.text
    assert "둘째 문단입니다." in result.text


def test_extract_hwpx_keeps_text_after_inline_linebreak():
    """실제 규격서 표에서 발견(2026-09-05): <hp:t>안에 <hp:lineBreak/>가 있으면 ElementTree가
    텍스트를 text/tail로 쪼갠다 — .text만 읽으면 태그 뒤 내용이 통째로 사라진다. 실제 사례:
    "국제공동연구개발비를 제외한 <hp:lineBreak/>연구개발비의 100분의 75 이하"에서 핵심 수치
    "100분의 75"가 유실됐었음."""
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?><hs:sec xmlns:hs="ns" xmlns:hp="{_HWPX_NS}">'
        "<hp:p><hp:run><hp:t>국제공동연구개발비를 제외한 <hp:lineBreak/>연구개발비의 100분의 75 이하</hp:t></hp:run></hp:p>"
        "</hs:sec>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", xml)
    result = extract_document("표.hwpx", buf.getvalue())
    assert result.ok is True
    assert "100분의 75 이하" in result.text
    assert "국제공동연구개발비를 제외한 연구개발비의 100분의 75 이하" in result.text


def test_extract_hwpx_no_sections_reports_failure_not_silent_empty():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("unrelated.txt", "x")
    result = extract_document("빈파일.hwpx", buf.getvalue())
    assert result.ok is False
    assert result.text is None
    assert result.error  # 조용한 빈 결과 금지 — 이유가 남아야 한다


_DOCX_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _make_docx(paragraphs: list[str]) -> bytes:
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{_DOCX_NS}"><w:body>'
        + "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
        + "</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_extract_docx_joins_paragraph_text():
    """2026-09-05 추가 — 고객 소개서 업로드용, 지금까지 .docx는 아예 지원 목록에 없었다."""
    content = _make_docx(["회사 소개 문단입니다.", "제품 소개 문단입니다."])
    result = extract_document("회사소개서.docx", content)
    assert result.ok is True
    assert result.method == "docx_xml"
    assert "회사 소개 문단입니다." in result.text
    assert "제품 소개 문단입니다." in result.text


def test_extract_docx_no_document_xml_reports_failure_not_silent_empty():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("unrelated.txt", "x")
    result = extract_document("빈파일.docx", buf.getvalue())
    assert result.ok is False
    assert result.text is None
    assert result.error


def test_extract_pdf_success_uses_pypdf_text_layer():
    fake_page = mock.Mock()
    fake_page.extract_text.return_value = "추출된 공고문 내용"
    with mock.patch("app.services.document_extract.PdfReader") as MockReader:
        MockReader.return_value.pages = [fake_page]
        result = extract_document("공고문.pdf", b"%PDF-fake")
    assert result.ok is True
    assert result.method == "pdf_text"
    assert result.text == "추출된 공고문 내용"


def test_extract_pdf_empty_text_layer_falls_back_to_ocr_not_immediate_failure():
    # 2026-09-10 OCR 도입 전에는 텍스트 레이어가 비면 바로 "스캔본 가능성"으로 실패 처리했는데,
    # 이제는 스캔본일 가능성이 실제로 높으므로 조용히 포기하지 않고 OCR을 시도한다 — 이 테스트가
    # 실제 검증하는 건 "OCR로 폴백까지 실제로 넘어간다"는 것(OCR 자체 성공/실패는 아래 별도
    # 테스트들이 검증). 여기선 PdfReader만 모킹하고 fitz는 진짜 빈 PDF를 열게 둔다.
    fake_page = mock.Mock()
    fake_page.extract_text.return_value = ""
    with mock.patch("app.services.document_extract.PdfReader") as MockReader:
        MockReader.return_value.pages = [fake_page]
        with mock.patch("app.services.document_extract.pytesseract.image_to_string", return_value="OCR로 복구된 내용"):
            result = extract_document("스캔본.pdf", _make_pdf(page_count=1))
    assert result.ok is True
    assert result.method == "pdf_ocr"
    assert "OCR로 복구된 내용" in result.text


def test_extract_pdf_broken_file_reports_error_not_exception():
    with mock.patch("app.services.document_extract.PdfReader", side_effect=ValueError("broken pdf")):
        result = extract_document("깨진파일.pdf", b"not a pdf")
    assert result.ok is False
    assert result.error == "broken pdf"


def test_extract_hwp_preview_success_decodes_utf16le():
    fake_stream = io.BytesIO("과학기술정보통신부 공고".encode("utf-16-le"))
    fake_ole = mock.MagicMock()
    fake_ole.exists.return_value = True
    fake_ole.openstream.return_value = fake_stream
    fake_ole.__enter__.return_value = fake_ole
    with mock.patch("app.services.document_extract.olefile.OleFileIO", return_value=fake_ole):
        result = extract_document("구버전공고.hwp", b"\xd0\xcf\x11\xe0fake-ole")
    assert result.ok is True
    assert result.method == "hwp_preview"
    assert result.text == "과학기술정보통신부 공고"


def test_extract_hwp_preview_missing_stream_reports_failure():
    fake_ole = mock.MagicMock()
    fake_ole.exists.return_value = False
    fake_ole.__enter__.return_value = fake_ole
    with mock.patch("app.services.document_extract.olefile.OleFileIO", return_value=fake_ole):
        result = extract_document("이상한파일.hwp", b"\xd0\xcf\x11\xe0fake-ole")
    assert result.ok is False
    assert "PrvText" in result.error


def _fake_hwp5proc_xml_run(xml_body: str):
    """subprocess.run(["hwp5proc", "xml", ..., "--output", <path>]) 모킹 — 실제로 그 경로에
    XML을 써서 뒤이은 ElementTree.parse(dest)가 읽을 수 있게 한다."""

    def _run(args, **kwargs):
        out_path = args[args.index("--output") + 1]
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(xml_body)
        return mock.Mock(returncode=0)

    return _run


def test_extract_hwp_prefers_hwp5xml_full_text_over_preview():
    # 2026-09-04 — LibreOffice는 이 배포판에서 HWP5를 아예 못 열어(구버전 필터만 등록됨,
    # 실제 나라장터 첨부문서로 확인) pyhwp로 교체했다. 처음엔 hwp5txt CLI(plaintext.xsl)를
    # 썼는데 표(TableControl) 내용을 통째로 버리는 걸 발견해(2026-09-05, 로봇산업기술개발사업
    # 실제 공고에서 "세부사업(내역사업)" 등 핵심 정보가 표에만 있었음) hwp5proc xml로 전체
    # XML 모델을 뽑아 직접 걷는 방식으로 교체 — 표 내용까지 복원된다.
    xml_body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<HwpDoc><BodyText><Paragraph><LineSeg><Text>hwp5xml로 추출된 전문 텍스트</Text></LineSeg></Paragraph></BodyText></HwpDoc>"
    )
    with mock.patch("app.services.document_extract.subprocess.run", side_effect=_fake_hwp5proc_xml_run(xml_body)):
        result = extract_document("공고문.hwp", b"\xd0\xcf\x11\xe0fake-ole")
    assert result.ok is True
    assert result.method == "hwp5xml"
    assert result.text == "hwp5xml로 추출된 전문 텍스트"


def test_extract_hwp_renders_table_cells_instead_of_placeholder():
    # 실제 규격서 표 구조 재현: TableBody > TableRow > TableCell > Paragraph > LineSeg > Text.
    xml_body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<HwpDoc><BodyText><Paragraph><LineSeg><TableControl><TableBody rows=\"1\" cols=\"2\">"
        "<TableRow>"
        "<TableCell col=\"0\" row=\"0\"><Paragraph><LineSeg><Text>세부사업</Text></LineSeg></Paragraph></TableCell>"
        "<TableCell col=\"1\" row=\"0\"><Paragraph><LineSeg><Text>로봇산업기술개발</Text></LineSeg></Paragraph></TableCell>"
        "</TableRow>"
        "</TableBody></TableControl></LineSeg></Paragraph></BodyText></HwpDoc>"
    )
    with mock.patch("app.services.document_extract.subprocess.run", side_effect=_fake_hwp5proc_xml_run(xml_body)):
        result = extract_document("공고문.hwp", b"\xd0\xcf\x11\xe0fake-ole")
    assert result.ok is True
    assert "세부사업 | 로봇산업기술개발" in result.text


def test_extract_hwp_falls_back_to_preview_when_hwp5txt_unavailable():
    fake_stream = io.BytesIO("미리보기 텍스트".encode("utf-16-le"))
    fake_ole = mock.MagicMock()
    fake_ole.exists.return_value = True
    fake_ole.openstream.return_value = fake_stream
    fake_ole.__enter__.return_value = fake_ole
    with mock.patch("app.services.document_extract.subprocess.run", side_effect=FileNotFoundError()):
        with mock.patch("app.services.document_extract.olefile.OleFileIO", return_value=fake_ole):
            result = extract_document("구버전공고.hwp", b"\xd0\xcf\x11\xe0fake-ole")
    assert result.ok is True
    assert result.method == "hwp_preview"
    assert result.text == "미리보기 텍스트"


def test_extract_hwp_falls_back_to_preview_when_hwp5txt_returns_nonzero():
    fake_stream = io.BytesIO("미리보기 텍스트".encode("utf-16-le"))
    fake_ole = mock.MagicMock()
    fake_ole.exists.return_value = True
    fake_ole.openstream.return_value = fake_stream
    fake_ole.__enter__.return_value = fake_ole
    fake_proc = mock.Mock(returncode=1, stdout=b"")
    with mock.patch("app.services.document_extract.subprocess.run", return_value=fake_proc):
        with mock.patch("app.services.document_extract.olefile.OleFileIO", return_value=fake_ole):
            result = extract_document("깨진HWP.hwp", b"\xd0\xcf\x11\xe0fake-ole")
    assert result.ok is True
    assert result.method == "hwp_preview"


def test_extract_document_unsupported_extension_reports_failure_not_silent_skip():
    result = extract_document("신청서양식.zip", b"PK\x03\x04fake")
    assert result.ok is False
    assert result.method == "unsupported"
    assert "지원하지 않는 형식" in result.error


def _make_png(size: tuple[int, int] = (100, 40)) -> bytes:
    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new("RGB", size, color="white").save(buf, format="PNG")
    return buf.getvalue()


def _make_pdf(page_count: int = 1) -> bytes:
    import pymupdf as fitz

    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page()
    content = doc.tobytes()
    doc.close()
    return content


def test_extract_image_ocr_success_returns_recognized_text():
    # 2026-09-10 OCR 도입 — 실제 Tesseract 엔진 정확도는 검증 대상이 아니라(다른 라이브러리
    # 파서들과 동일한 모킹 방침), 우리 쪽 래핑 로직(호출·정리·실패 판정)만 검증한다.
    with mock.patch("app.services.document_extract.pytesseract.image_to_string", return_value="  붙임 규격서 내용  \n") as mock_ocr:
        result = extract_document("규격서_스캔.jpg", _make_png())
    assert result.ok is True
    assert result.method == "tesseract_ocr"
    assert result.text == "붙임 규격서 내용"
    assert mock_ocr.call_args.kwargs.get("lang") == "kor+eng"


def test_extract_image_ocr_empty_result_reports_failure_not_silent():
    with mock.patch("app.services.document_extract.pytesseract.image_to_string", return_value=""):
        result = extract_document("빈이미지.png", _make_png())
    assert result.ok is False
    assert result.method == "tesseract_ocr"
    assert "OCR 결과가 비어" in result.error


def test_extract_image_ocr_engine_error_reports_failure_not_exception():
    with mock.patch("app.services.document_extract.pytesseract.image_to_string", side_effect=RuntimeError("tesseract not found")):
        result = extract_document("깨진이미지.png", _make_png())
    assert result.ok is False
    assert result.method == "tesseract_ocr"
    assert "tesseract not found" in result.error


def test_extract_pdf_falls_back_to_ocr_when_text_layer_empty():
    # 스캔본 PDF(텍스트 레이어 없음)는 바로 실패 처리하지 않고 페이지를 이미지로 렌더링해 OCR한다.
    with mock.patch("app.services.document_extract.pytesseract.image_to_string", return_value="스캔된 공고문 본문"):
        result = extract_document("스캔공고.pdf", _make_pdf(page_count=1))
    assert result.ok is True
    assert result.method == "pdf_ocr"
    assert "스캔된 공고문 본문" in result.text


def test_extract_pdf_ocr_also_empty_reports_final_failure_not_silent():
    with mock.patch("app.services.document_extract.pytesseract.image_to_string", return_value=""):
        result = extract_document("완전백지.pdf", _make_pdf(page_count=1))
    assert result.ok is False
    assert result.method == "pdf_ocr"
    assert "OCR" in result.error


def test_extract_pdf_ocr_limits_to_max_pages_and_notes_truncation():
    from app.services import document_extract

    over_limit = document_extract._PDF_OCR_MAX_PAGES + 3
    with mock.patch("app.services.document_extract.pytesseract.image_to_string", return_value="페이지 내용") as mock_ocr:
        result = extract_document("초대용량스캔.pdf", _make_pdf(page_count=over_limit))
    assert result.ok is True
    assert mock_ocr.call_count == document_extract._PDF_OCR_MAX_PAGES
    assert f"{document_extract._PDF_OCR_MAX_PAGES}페이지만 처리" in result.text
