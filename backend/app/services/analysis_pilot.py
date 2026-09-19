"""S8 심층 분석 파일럿(A0+A1만) — 구현스펙 07절 전체(A0~A7) 중 "실제 사이트에서 웹페이지+
첨부문서를 받아 텍스트로 추출"까지만 하는 첫 단계. LLM 호출(A2 이후)은 이번 범위 밖 —
ANTHROPIC_API_KEY가 아직 없기도 하고, 사용자가 "추출까지만" 하자고 확정함.

지원 소스 2군: IRIS(2026-09-03)와 나라장터 g2b 계열(2026-09-04~09-06). IRIS는 상세페이지
HTML의 JS onclick(f_bsnsAncm_downloadAtchFile)에 파일ID가 박혀 있어 페이지를 직접 파싱한다.
g2b 계열(입찰공고·사전규격·발주계획) 첨부 발견 로직은 이 파일의 500줄 상한 때문에
`app/services/g2b_attachments.py`로 분리했다(2026-09-08) — 그쪽 모듈 docstring에 각 계열별
필드·오퍼레이션 상세가 있다.

원본 파일은 저장하지 않는다(2026-09-03 결정) — notice.url이 항상 있어 필요하면 재다운로드
가능하고, 저장공간이 무한정 느는 것도 피한다. 추출된 텍스트만 analysis_doc.text에 남는다.

첨부 필터링(2026-09-05, 사용자 지시) — 공고 "내용" 분석이 목적이라 서식·매뉴얼처럼 누구나
아는 일반 안내 문서는 건너뛴다(_SKIP_NAME_KEYWORDS). zip은 더 이상 통째로 건너뛰지 않는다 —
이름이 걸러지지 않으면(예: "제안요청서(RFP) 등 관련서식.zip") 열어서 안의 모든 파일을
개별적으로 추출한다(내부 파일에도 같은 이름 필터 적용).

IRIS 상세페이지 "공고문" 폴백(2026-09-12, 사용자 지시) — "모든 내용은 첨부파일에 다 들어
있으니, 첨부파일 다운로드/추출이 실패한 경우에만" 상세페이지의 "■ 공고문" 섹션(스마트에디터로
작성된 자유서술 본문, `class="se-contents"`)을 대체 텍스트로 쓴다. 실측 확인(2026-09-12,
IRIS 공고 2건): 이 클래스는 페이지에 정확히 1번만 나타나 "공고문" 섹션만 정확히 골라낼 수
있고, "사업담당자/연락처"(PII) 필드는 완전히 별도 위치(`<li>` 항목)에 있어 이 섹션 안에는
섞여 들어오지 않는다. g2b.go.kr 상세페이지는 반대로 WebSquare SPA라 정적으로 받은 HTML에
메뉴 정의 데이터만 있고 실제 공고 내용은 JS가 별도 API를 호출해 그려서(Playwright 미도입
상태론 접근 불가, 2026-09-12 재확인) 같은 폴백을 적용할 수 없다.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, unquote

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.models import analysis, analysis_doc, notice
from app.security.url_guard import fetch
from app.services.document_extract import extract_document
from app.services.g2b_attachments import _discover_g2b_attachments, _should_skip_by_name
from app.services.notice_topic_scoring import rescan_notice_topics_from_documents

_IRIS_ATCH_RE = re.compile(
    r"f_bsnsAncm_downloadAtchFile\('([^']+)','([^']+)','([^']+)'\s*,'(\d+)'\)"
)
_MAX_DOC_BYTES = 50 * 1024 * 1024  # 문서 다운로드는 url_guard 기본 10MB보다 상향(스펙 주석과 동일 원칙)


class AnalysisInProgressError(Exception):
    """동일 공고에 이미 진행 중인 분석이 있음 — 중복 실행 거부(S8 원칙 3)."""


class UnsupportedSourceError(Exception):
    """이 파일럿이 아직 지원하지 않는 사이트(IRIS·나라장터 입찰공고정보서비스 외)."""


def _discover_iris_attachments(html: str) -> list[dict]:
    """일반 안내 문서(_should_skip_by_name)만 여기서 제외 — zip은 더 이상 제외하지 않는다
    (내부 파일까지 run_extraction_pilot에서 펼쳐서 분석)."""
    found = []
    for atch_doc_id, atch_file_id, file_name, _file_size in _IRIS_ATCH_RE.findall(html):
        if _should_skip_by_name(file_name):
            continue
        download_url = (
            "https://www.iris.go.kr/comm/file/fileDownload.do"
            f"?atchDocId={quote(atch_doc_id)}&atchFileId={quote(atch_file_id)}"
        )
        found.append({"name": file_name, "download_url": download_url, "inline_text": None})
    return found


class _IrisNoticeBodyParser(HTMLParser):
    """`class="se-contents"` div 하나만 골라 텍스트로 뽑는다. bs4/lxml 없이 표준 라이브러리만
    사용 — div 중첩 깊이를 세어 안쪽 `</div>`에서 엉뚱하게 잘리지 않게 한다."""

    def __init__(self) -> None:
        super().__init__()
        self._in_target = False
        self._depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            if self._in_target and tag in ("br", "p", "tr", "li"):
                self._chunks.append("\n")
            return
        if not self._in_target:
            classes = (dict(attrs).get("class") or "").split()
            if "se-contents" in classes:
                self._in_target = True
                self._depth = 1
            return
        self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._in_target and tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self._in_target = False

    def handle_data(self, data: str) -> None:
        if self._in_target and data.strip():
            self._chunks.append(data.strip())

    @property
    def text(self) -> str:
        return "\n".join(self._chunks).strip()


def _extract_iris_notice_body(html: str) -> str | None:
    parser = _IrisNoticeBodyParser()
    parser.feed(html)
    return parser.text or None


def _kind_from_filename(filename: str) -> str:
    lower = filename.lower()
    for ext in ("pdf", "hwpx", "hwp", "pptx", "xlsx", "zip"):
        if lower.endswith(f".{ext}"):
            return ext
    return "other"


_CONTENT_DISPOSITION_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.IGNORECASE)


def _filename_from_content_disposition(headers, fallback: str) -> str:
    """사전규격정보서비스처럼 URL에 파일명이 없어(2026-09-09 실측 — 오늘 배치 325건 전부
    specDocFileUrl에 fileNm 파라미터 없음) `_filename_from_url`이 확장자 없는 "규격서1" 같은
    이름으로 대체하면, 확장자가 없어 _kind_from_filename이 "other"로 판정해 지원 형식이 있는
    파일도 무조건 "지원하지 않는 형식"으로 추출 실패하던 문제 — 실제 다운로드 응답의
    Content-Disposition 헤더엔 진짜 파일명(확장자 포함)이 있음을 직접 확인해 여기서 보완한다.
    이미 확장자를 아는 이름(ntceSpecFileNm 등 정상 케이스)은 그대로 두고 건드리지 않는다."""
    disposition = headers.get("Content-Disposition") or headers.get("content-disposition")
    if not disposition:
        return fallback
    match = _CONTENT_DISPOSITION_RE.search(disposition)
    if not match:
        return fallback
    try:
        decoded = unquote(match.group(1)).strip()
    except Exception:  # noqa: BLE001 — 디코딩 실패해도 원래 이름 유지, 조용히 죽지 않음
        return fallback
    return decoded or fallback


def _extract_one(name: str, content: bytes) -> dict:
    """파일 하나(zip 안에서 나온 파일 포함)를 추출해 analysis_doc 한 행분 dict로 만든다."""
    name = name[:255]  # analysis_doc.name 컬럼 상한(zip파일명 :: 내부경로 접두어로 길어질 수 있음)
    doc_row = {
        "name": name, "kind": _kind_from_filename(name), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
        "extract_method": None, "extract_ok": False, "error": None, "text": None,
    }
    try:
        result = extract_document(name, content)
        doc_row["extract_method"] = result.method
        doc_row["extract_ok"] = result.ok
        # PostgreSQL text 컬럼은 NUL(\x00) 바이트를 거부한다 — pypdf가 특정 PDF 인코딩(자간
        # 조정용 더미 글자 등)을 \x00으로 잘못 디코딩하는 사례가 실측 확인됨(2026-09-05,
        # IRIS 대량 재수집 중 발견). 여기서 안 걸러내면 이 아래 analysis_doc INSERT가 예외를
        # 던지는데 그 예외가 try 블록 밖이라(호출부 runner.py가 통째로 삼킴) analysis가
        # "running"에 영원히 멈추는 사고로 이어졌다 — 원본 의미 손실 없이 제거만 한다.
        doc_row["text"] = result.text.replace("\x00", "") if result.text else result.text
        doc_row["error"] = result.error
    except Exception as exc:  # noqa: BLE001 — 폴백 사슬 마지막 보고 지점, 조용히 삼키지 않는다
        doc_row["error"] = str(exc)
    return doc_row


def _decode_zip_name(info: zipfile.ZipInfo) -> str:
    """한글 zip 파일명 깨짐 수정(2026-09-07 발견) — Windows에서 만든 zip은 내부 파일명을
    CP949(EUC-KR)로 인코딩하면서도 UTF-8 플래그(flag_bits 0x800)는 안 세워두는 경우가
    흔하다. zipfile은 그 플래그가 없으면 항상 CP437로 디코딩해버려 한글이 깨진다 — CP437로
    되돌려 바이트로 만든 뒤 CP949로 다시 디코딩한다. UTF-8 플래그가 있으면(zipfile이 이미
    올바르게 디코딩) 그대로 둔다."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return info.filename  # 복구 실패해도 예외로 전체를 막지 않고 원본(깨진 이름) 그대로


_MAX_ZIP_NESTING_DEPTH = 3  # zip 안에 zip이 무한히 깊어지는 이상 파일(zip bomb 등) 방지


def _iter_zip_entries(content: bytes, *, _depth: int = 0) -> list[tuple[str, bytes]]:
    """zip 안의 각 파일을 (내부경로, 바이트)로 펼친다 — 디렉터리 항목·일반 안내 문서(이름 필터
    적용)는 뺀다(2026-09-05, "분석 대상 파일이 zip이면 안의 모든 파일을 분석"). 손상된 zip은
    예외를 그대로 올려 호출부가 실패로 기록하게 한다.

    2026-09-11 실측 — "계약 관련 서류.zip" 안에 "용역계약일반조건.zip"처럼 zip 안에 또 zip이
    든 실제 사례(31건)가 있었다. extract_document()는 .zip 확장자를 아예 모르기 때문에 그때
    까지는 그 안쪽 zip이 통째로 "지원하지 않는 형식"으로 실패 처리됐다 — 재귀적으로 한 번
    더 펼친다(상한 _MAX_ZIP_NESTING_DEPTH). 안쪽 zip 자체가 손상됐으면 예외를 삼키고 그
    zip 파일 자체를 leaf로 남겨(기존과 동일하게 "지원하지 않는 형식"으로 실패 보고) 조용히
    사라지지 않게 한다."""
    entries = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            inner_name = _decode_zip_name(info)
            if _should_skip_by_name(inner_name):
                continue
            inner_content = z.read(info)
            if inner_name.lower().endswith(".zip") and _depth < _MAX_ZIP_NESTING_DEPTH:
                try:
                    nested_entries = _iter_zip_entries(inner_content, _depth=_depth + 1)
                    entries.extend((f"{inner_name} :: {name}", data) for name, data in nested_entries)
                    continue
                except Exception:  # noqa: BLE001 — 안쪽 zip이 손상됐으면 leaf로 남겨 기존 방식대로 실패 보고
                    pass
            entries.append((inner_name, inner_content))
    return entries


def run_extraction_pilot(conn: Connection, notice_id: int, *, prefetched_raw_item: dict | None = None) -> dict:
    """A0(입력 준비)+A1(문서 추출)만 수행하고 analysis/analysis_doc에 남긴다.

    한 트랜잭션 안에서 동기로 전부 처리한다 — 아직 백그라운드 워커가 없어서(CLAUDE.md:
    Redis·Celery 도입 금지, 큐가 필요하면 DB 테이블) 진짜 동시 요청 경합까지 완벽히 막지는
    못하지만(같은 트랜잭션이라 "진행 중" 표시를 커밋하기 전엔 다른 요청이 못 봄), 사람이
    버튼을 눌러서 시작하는 이번 파일럿 범위에선 충분하다.

    prefetched_raw_item(2026-09-08) — g2b 계열(입찰공고·사전규격·발주계획) 공고를 방금
    수집한 직후 처리할 때, 수집 시점에 이미 받아둔 원본 API 항목을 그대로 넘기면 이 함수가
    같은 데이터를 다시 실시간 재조회하지 않는다(app/services/pending_analysis.py
    process_new_notices가 넘겨줌). IRIS는 애초에 공고별 상세페이지를 긁는 방식이라 재조회
    자체가 불필요한 중복이 아니므로 이 최적화 대상이 아니다.
    """
    row = conn.execute(
        select(
            notice.c.url, notice.c.source_id, notice.c.notice_no, notice.c.open_dt, notice.c.created_at, notice.c.extra
        ).where(notice.c.id == notice_id)
    ).first()
    if row is None:
        raise ValueError(f"공고를 찾을 수 없음: {notice_id}")
    notice_url = row.url

    if "iris.go.kr" not in notice_url and "g2b.go.kr" not in notice_url:
        raise UnsupportedSourceError("이 파일럿은 아직 IRIS·나라장터 입찰공고정보서비스 공고만 지원합니다.")

    existing = conn.execute(
        select(analysis.c.id).where(analysis.c.notice_id == notice_id, analysis.c.status.in_(("queued", "running")))
    ).first()
    if existing:
        raise AnalysisInProgressError(f"이미 진행 중인 분석이 있습니다(analysis id={existing.id}).")

    next_ver = conn.execute(
        select(analysis.c.ver).where(analysis.c.notice_id == notice_id).order_by(analysis.c.ver.desc())
    ).first()
    ver = (next_ver.ver + 1) if next_ver else 1

    analysis_id = conn.execute(
        analysis.insert().values(
            notice_id=notice_id,
            source_kind="notice",
            input_ref=notice_url,
            status="running",
            step="A1_extract",
            started_at=datetime.now(timezone.utc),
            ver=ver,
        ).returning(analysis.c.id)
    ).scalar_one()

    is_iris = "iris.go.kr" in notice_url
    iris_html: str | None = None
    try:
        if is_iris:
            iris_html = fetch(notice_url).text
            attachments = _discover_iris_attachments(iris_html)
        else:
            anchor_dt = row.open_dt or row.created_at
            attachments = _discover_g2b_attachments(
                conn, row.source_id, row.notice_no, row.extra, anchor_dt, prefetched_item=prefetched_raw_item
            )
    except Exception as exc:  # noqa: BLE001 — 여기서 안 잡으면 analysis가 "running"에 영원히
        # 멈춘다(2026-09-05, 자동 실행 도입으로 사람이 재시도 안 하는 경우가 생겨 더 중요해짐).
        conn.execute(
            analysis.update()
            .where(analysis.c.id == analysis_id)
            .values(status="failed", step="A1_extract", finished_at=datetime.now(timezone.utc), verdict=str(exc))
        )
        return {"analysis_id": analysis_id, "status": "failed", "attachments_found": 0, "docs": [], "error": str(exc)}

    docs_result = []
    any_ok = False
    try:
        # SAVEPOINT로 감싼다 — analysis_doc INSERT 자체가 DB 레벨 예외(예: NUL 바이트 등
        # 예상 못 한 데이터 문제)로 실패하면 커넥션의 트랜잭션이 "aborted" 상태가 되어, 아래
        # except 블록에서 analysis를 failed로 표시하려는 UPDATE조차 막힌다(2026-09-05, IRIS
        # 대량 재수집 중 PDF의 NUL 바이트로 실제 발생 — analysis가 "running"에 영구히 멈춤).
        # begin_nested()면 실패해도 이 구간만 롤백되고 커넥션은 계속 쓸 수 있다.
        with conn.begin_nested():
            for task in attachments:
                file_name = task["name"]

                # 발주계획현황서비스처럼 다운로드가 아니라 API 응답 텍스트 그 자체가 문서인
                # 경우(2026-09-06) — 다운로드·추출 없이 그대로 analysis_doc에 남긴다.
                if task["inline_text"] is not None:
                    text = task["inline_text"].replace("\x00", "")  # PDF NUL 사고와 같은 이유로 방어
                    text_bytes = text.encode("utf-8")
                    doc_row = {
                        "name": file_name[:255], "kind": "text", "bytes": len(text_bytes),
                        "sha256": hashlib.sha256(text_bytes).hexdigest(), "extract_method": "api_inline_text",
                        "extract_ok": bool(text.strip()), "error": None, "text": text or None,
                    }
                    any_ok = any_ok or doc_row["extract_ok"]
                    conn.execute(analysis_doc.insert().values(analysis_id=analysis_id, **doc_row))
                    docs_result.append(doc_row)
                    continue

                download_url = task["download_url"]
                try:
                    response = fetch(download_url, max_bytes=_MAX_DOC_BYTES)
                    content = response.content
                except Exception as exc:  # noqa: BLE001 — 폴백 사슬 마지막 보고 지점, 조용히 삼키지 않는다
                    doc_row = {
                        "name": file_name, "kind": _kind_from_filename(file_name), "bytes": 0, "sha256": "",
                        "extract_method": None, "extract_ok": False, "error": str(exc), "text": None,
                    }
                    conn.execute(analysis_doc.insert().values(analysis_id=analysis_id, **doc_row))
                    docs_result.append(doc_row)
                    continue

                if _kind_from_filename(file_name) == "other":
                    # URL에 파일명이 없어 확장자 없는 대체 이름(예: "규격서1")을 쓴 경우 —
                    # 실제 다운로드 응답의 Content-Disposition에서 진짜 파일명을 보완한다.
                    file_name = _filename_from_content_disposition(response.headers, file_name)
                    # 2026-09-20 — 공통문서 필터(_should_skip_by_name)는 다운로드 *전에* 이
                    # 대체 이름("규격서1")으로 이미 한 번 통과했다("양식" 등 키워드가 안 걸림).
                    # 실제 파일명("2. 투찰내역서(양식).xlsm")은 다운로드 응답에서야 드러나서
                    # 재검사 없이 그대로 추출로 넘어갔다 — 그 결과 엑셀 서식 파일의 내부 XML이
                    # 통째로 텍스트로 뽑혀 건당 450만자짜리 노이즈가 쌓였다(실측 4건, A2 컨텍스트
                    # 낭비의 실제 원인). 진짜 이름을 알게 된 지금 다시 한번 걸러낸다.
                    if _should_skip_by_name(file_name):
                        doc_row = {
                            "name": file_name, "kind": _kind_from_filename(file_name), "bytes": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(), "extract_method": None,
                            "extract_ok": False, "error": "공통 문서로 판단되어 제외(실제 파일명 확인 후)",
                            "text": None,
                        }
                        conn.execute(analysis_doc.insert().values(analysis_id=analysis_id, **doc_row))
                        docs_result.append(doc_row)
                        continue

                if _kind_from_filename(file_name) == "zip":
                    # "분석 대상 파일이 zip이면 안의 모든 파일을 분석"(2026-09-05) — 개별 파일마다
                    # analysis_doc 행을 따로 남긴다(이름에 zip파일명을 접두어로 붙여 출처를 남김).
                    try:
                        inner_files = _iter_zip_entries(content)
                    except Exception as exc:  # noqa: BLE001
                        doc_row = {
                            "name": file_name, "kind": "zip", "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                            "extract_method": None, "extract_ok": False, "error": f"압축 해제 실패: {exc}", "text": None,
                        }
                        conn.execute(analysis_doc.insert().values(analysis_id=analysis_id, **doc_row))
                        docs_result.append(doc_row)
                        continue
                    for inner_name, inner_content in inner_files:
                        doc_row = _extract_one(f"{file_name} :: {inner_name}", inner_content)
                        any_ok = any_ok or doc_row["extract_ok"]
                        conn.execute(analysis_doc.insert().values(analysis_id=analysis_id, **doc_row))
                        docs_result.append(doc_row)
                else:
                    doc_row = _extract_one(file_name, content)
                    any_ok = any_ok or doc_row["extract_ok"]
                    conn.execute(analysis_doc.insert().values(analysis_id=analysis_id, **doc_row))
                    docs_result.append(doc_row)

            # IRIS 상세페이지 "공고문" 폴백(2026-09-12) — 첨부가 아예 없거나(attachments=0)
            # 있어도 전부 다운로드/추출 실패한(any_ok=False) 경우에만 발동. 첨부가 정상
            # 추출됐으면 이미 "모든 내용이 첨부파일에 들어있다"(사용자 확인)는 전제로 건드리지
            # 않는다.
            if is_iris and not any_ok and iris_html:
                body_text = _extract_iris_notice_body(iris_html)
                if body_text:
                    text_bytes = body_text.encode("utf-8")
                    doc_row = {
                        "name": "공고문(상세페이지)", "kind": "text", "bytes": len(text_bytes),
                        "sha256": hashlib.sha256(text_bytes).hexdigest(), "extract_method": "iris_detail_page_fallback",
                        "extract_ok": True, "error": None, "text": body_text,
                    }
                    any_ok = True
                    conn.execute(analysis_doc.insert().values(analysis_id=analysis_id, **doc_row))
                    docs_result.append(doc_row)
    except Exception as exc:  # noqa: BLE001 — 조용한 실패 금지: "running"에 멈추는 대신 반드시 failed로 기록
        conn.execute(
            analysis.update()
            .where(analysis.c.id == analysis_id)
            .values(status="failed", step="A1_extract", finished_at=datetime.now(timezone.utc), verdict=str(exc))
        )
        return {"analysis_id": analysis_id, "status": "failed", "attachments_found": len(attachments), "docs": [], "error": str(exc)}

    final_status = "done" if (not attachments or any_ok) else "failed"
    conn.execute(
        analysis.update()
        .where(analysis.c.id == analysis_id)
        .values(status=final_status, step="A1_extract", finished_at=datetime.now(timezone.utc))
    )

    # 첨부문서 원문이 실제로 나온 경우에만 관심주제를 재채점한다(2026-09-10 사용자 지시) —
    # 첨부가 아예 없는 공고(any_ok=False, attachments=0)는 제목 기반 L2(수집 시점) 결과를
    # 그대로 둔다. 같은 트랜잭션에서 실행해 A1 성공과 재채점이 항상 같이 커밋되거나 같이
    # 롤백된다.
    if final_status == "done" and any_ok:
        rescan_notice_topics_from_documents(conn, notice_id, analysis_id)

    return {
        "analysis_id": analysis_id,
        "status": final_status,
        "attachments_found": len(attachments),
        "docs": docs_result,
    }


def get_latest_extraction(conn: Connection, notice_id: int) -> dict | None:
    """상세 페이지가 재방문 시에도 지난 추출 결과를 보여줄 수 있도록 최신 analysis 1건 + 문서."""
    row = conn.execute(
        select(analysis.c.id, analysis.c.status, analysis.c.step, analysis.c.finished_at, analysis.c.ver)
        .where(analysis.c.notice_id == notice_id)
        .order_by(analysis.c.ver.desc())
    ).first()
    if row is None:
        return None

    docs = conn.execute(
        select(
            analysis_doc.c.name,
            analysis_doc.c.kind,
            analysis_doc.c.extract_method,
            analysis_doc.c.extract_ok,
            analysis_doc.c.error,
            analysis_doc.c.text,
        ).where(analysis_doc.c.analysis_id == row.id)
    ).mappings().all()

    return {
        "analysis_id": row.id,
        "status": row.status,
        "step": row.step,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "ver": row.ver,
        "docs": [dict(d) for d in docs],
    }
