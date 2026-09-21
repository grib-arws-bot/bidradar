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


_SPREADSHEETML_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _make_xlsx(shared_strings: list[str]) -> bytes:
    sst_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?><sst xmlns="{_SPREADSHEETML_NS}">'
        + "".join(f"<si><t>{s}</t></si>" for s in shared_strings)
        + "</sst>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", sst_xml)
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


def test_extract_hwp_extension_with_zip_content_reroutes_to_hwpx():
    # 2026-09-11 실측 — 위 반대 방향도 확인됨: 실제로는 진짜 HWPX(zip, "mimetype:
    # application/hwp+zip"로 시작)인데 .hwp 확장자가 붙어 온다. OLE 파서로 열면
    # "not an OLE2 structured storage file"로 실패했었다.
    content = _make_hwpx(["확장자는 hwp인데 실제로는 HWPX"])
    result = extract_document("제안요청서.hwp", content)
    assert result.ok is True
    assert result.method == "hwpx_xml"
    assert result.text == "확장자는 hwp인데 실제로는 HWPX"


def test_extract_hwp_extension_with_real_ole_content_still_parses_as_hwp5():
    # 위 우회 로직이 "진짜" hwp(OLE 바이너리인 정상 케이스)까지 잘못 건드리면 안 된다.
    xml_body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<HwpDoc><BodyText><Paragraph><LineSeg><Text>정상적인 hwp5 파일</Text></LineSeg></Paragraph></BodyText></HwpDoc>"
    )
    with mock.patch("app.services.document_extract.subprocess.run", side_effect=_fake_hwp5proc_xml_run(xml_body)):
        result = extract_document("정상공고.hwp", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1fake-ole-body")
    assert result.ok is True
    assert result.method == "hwp5xml"


def test_extract_hwpx_extension_with_ole_content_reroutes_to_hwp5():
    # 2026-09-11 실측 — 나라장터가 실제로는 구버전 HWP5(OLE 바이너리) 파일에 .hwpx 확장자를
    # 잘못 붙여 주는 사례를 실데이터로 확인(매직바이트 D0 CF 11 E0 A1 B1 1A E1). 확장자만
    # 믿고 zip으로 열면 무조건 "File is not a zip file"로 실패했었다 — 내용을 먼저 확인해서
    # 진짜 형식으로 우회해야 한다.
    ole_content = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"fake-ole-body"
    xml_body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<HwpDoc><BodyText><Paragraph><LineSeg><Text>확장자는 hwpx인데 실제로는 HWP5</Text></LineSeg></Paragraph></BodyText></HwpDoc>"
    )
    with mock.patch("app.services.document_extract.subprocess.run", side_effect=_fake_hwp5proc_xml_run(xml_body)):
        result = extract_document("공고문1.hwpx", ole_content)
    assert result.ok is True
    assert result.method == "hwp5xml"
    assert result.text == "확장자는 hwpx인데 실제로는 HWP5"


def test_extract_hwpx_extension_with_real_zip_content_still_parses_as_hwpx():
    # 위 우회 로직이 "진짜" hwpx(정상적으로 zip인 경우)까지 잘못 건드리면 안 된다.
    content = _make_hwpx(["정상적인 hwpx 파일"])
    result = extract_document("정상공고.hwpx", content)
    assert result.ok is True
    assert result.method == "hwpx_xml"


def test_extract_xlsm_uses_same_parser_as_xlsx():
    # 2026-09-11 실측 15건 — 매크로 포함 엑셀(.xlsm)은 시트/셀 XML 구조가 .xlsx와 완전히
    # 같아서 별도 파서 없이 그대로 처리 가능한데 지금까지 "지원하지 않는 형식"으로 실패했다.
    content = _make_xlsx(["산출내역서 항목", "단가"])
    result = extract_document("산출내역서.xlsm", content)
    assert result.ok is True
    assert result.method == "xlsx_xml"
    assert "산출내역서 항목" in result.text


def test_extract_txt_decodes_utf8():
    result = extract_document("과업내용서_수정안내.txt", "과업내용서 내용이 일부 수정되었습니다.".encode("utf-8"))
    assert result.ok is True
    assert result.method == "plain_text"
    assert result.text == "과업내용서 내용이 일부 수정되었습니다."


def test_extract_txt_falls_back_to_cp949_for_legacy_korean_encoding():
    # 오래된 정부 문서는 UTF-8이 아니라 CP949(EUC-KR)로 저장된 경우가 흔하다.
    result = extract_document("공지사항.txt", "안내문 내용입니다.".encode("cp949"))
    assert result.ok is True
    assert result.text == "안내문 내용입니다."


def test_extract_txt_empty_file_reports_failure_not_silent():
    result = extract_document("빈파일.txt", b"")
    assert result.ok is False
    assert result.method == "plain_text"


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


# ---- 문서 내 이미지 OCR(2026-09-21, 의사결정_로그 193번) ----------------------------------


def _make_hwpx_with_image(paragraphs: list[str], *, image_size=(200, 200)) -> bytes:
    content = _make_hwpx(paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as src, zipfile.ZipFile(buf, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
        dst.writestr("BinData/image1.png", _make_png(image_size))
    return buf.getvalue()


def _make_pdf_with_image(*, image_size=(200, 200)) -> bytes:
    # 텍스트 레이어를 반드시 같이 넣어야 한다 — 텍스트가 없으면 _extract_pdf가 이 새 이미지
    # OCR 경로가 아니라 기존 "텍스트 레이어 없음 → 전체 페이지 OCR" 폴백으로 빠져서, 검증
    # 대상인 _extract_pdf_embedded_images_ocr()를 실제로는 안 거치게 된다. 영문으로 쓰는 이유 —
    # PyMuPDF의 기본 내장 폰트(helv)가 한글 글리프를 지원하지 않아 insert_text에 한글을
    # 쓰면 깨진다(별도 한글 폰트 등록이 필요한데 이 테스트의 관심사가 아님).
    import pymupdf as fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "PDF TEXT LAYER BODY")
    page.insert_image(fitz.Rect(0, 100, 100, 200), stream=_make_png(image_size))
    content = doc.tobytes()
    doc.close()
    return content


def test_extract_hwpx_appends_ocr_text_from_embedded_image():
    content = _make_hwpx_with_image(["본문 문단입니다."])
    with mock.patch(
        "app.services.document_extract.pytesseract.image_to_string", return_value="도표 안의 글자"
    ):
        result = extract_document("도표포함.hwpx", content)
    assert result.ok is True
    assert "본문 문단입니다." in result.text
    assert "도표 안의 글자" in result.text


def test_extract_hwpx_with_only_image_and_no_paragraphs_still_succeeds():
    """본문 문단이 하나도 없고(빈 섹션) 그림만 있는 hwpx는 기존엔 "추출된 텍스트가 비어
    있음"으로 실패 처리됐다 — 이미지 OCR을 덧붙이면서 이 경우도 살아나야 한다. 섹션 XML
    자체가 아예 없는 경우(malformed hwpx)와는 다른 시나리오 — 그건 여전히 별도 실패로
    남아야 한다(아래 test_extract_hwpx_no_sections_reports_failure_not_silent_empty)."""
    content = _make_hwpx([])  # 섹션은 있지만 문단 없음
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as src, zipfile.ZipFile(buf, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
        dst.writestr("BinData/image1.png", _make_png((200, 200)))
    with mock.patch(
        "app.services.document_extract.pytesseract.image_to_string", return_value="이미지뿐인 문서의 글자"
    ):
        result = extract_document("이미지만.hwpx", buf.getvalue())
    assert result.ok is True
    assert "이미지뿐인 문서의 글자" in result.text


def test_extract_hwpx_skips_small_decorative_images():
    """로고·구분선처럼 작은 이미지는 OCR 노이즈만 늘리므로 최소 크기 미만은 건너뛴다."""
    from app.services import document_extract

    tiny = (document_extract._MIN_EMBEDDED_IMAGE_DIM - 10, document_extract._MIN_EMBEDDED_IMAGE_DIM - 10)
    content = _make_hwpx_with_image(["본문입니다."], image_size=tiny)
    with mock.patch(
        "app.services.document_extract.pytesseract.image_to_string", return_value="작은이미지글자"
    ) as mock_ocr:
        result = extract_document("작은이미지.hwpx", content)
    assert result.ok is True
    assert "작은이미지글자" not in result.text
    mock_ocr.assert_not_called()


def test_extract_docx_appends_ocr_text_from_embedded_image():
    content = _make_docx(["워드 본문"])
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as src, zipfile.ZipFile(buf, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
        dst.writestr("word/media/image1.png", _make_png((200, 200)))
    with mock.patch("app.services.document_extract.pytesseract.image_to_string", return_value="워드 이미지 글자"):
        result = extract_document("워드문서.docx", buf.getvalue())
    assert result.ok is True
    assert "워드 본문" in result.text
    assert "워드 이미지 글자" in result.text


_PPTX_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def test_extract_pptx_appends_ocr_text_from_embedded_image():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "ppt/slides/slide1.xml",
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<p:sld xmlns:p="ns" xmlns:a="{_PPTX_DRAWINGML_NS}"><a:t>슬라이드 본문</a:t></p:sld>',
        )
        z.writestr("ppt/media/image1.png", _make_png((200, 200)))
    with mock.patch("app.services.document_extract.pytesseract.image_to_string", return_value="슬라이드 이미지 글자"):
        result = extract_document("발표자료.pptx", buf.getvalue())
    assert result.ok is True
    assert "슬라이드 본문" in result.text
    assert "슬라이드 이미지 글자" in result.text


def test_extract_pdf_appends_ocr_text_from_embedded_image():
    """텍스트 레이어가 있는 PDF라도, 페이지에 별도로 박힌 도표·캡처 이미지는 텍스트
    추출로는 안 잡힌다 — OCR해서 덧붙여야 한다."""
    doc_bytes = _make_pdf_with_image()
    with mock.patch(
        "app.services.document_extract.pytesseract.image_to_string", return_value="PDF 이미지 글자"
    ):
        result = extract_document("도표포함.pdf", doc_bytes)
    assert result.ok is True
    assert result.method == "pdf_text"  # 텍스트 레이어 경로를 그대로 탔는지(전체페이지 OCR 폴백이 아님) 확인
    assert "PDF TEXT LAYER BODY" in result.text
    assert "PDF 이미지 글자" in result.text


def test_extract_pdf_embedded_image_ocr_failure_does_not_break_text_extraction():
    """이미지 OCR이 실패해도(예: 손상된 이미지) 이미 성공한 텍스트 레이어 추출까지 실패로
    만들면 안 된다 — 보조 정보일 뿐 주 추출의 성패를 좌우하지 않는다."""
    doc_bytes = _make_pdf_with_image()
    with mock.patch(
        "app.services.document_extract.pytesseract.image_to_string", side_effect=RuntimeError("engine crashed")
    ):
        result = extract_document("이미지깨짐.pdf", doc_bytes)
    assert result.ok is True
    assert "PDF TEXT LAYER BODY" in result.text
