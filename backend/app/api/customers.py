"""라우터는 얇게 — S7 관심주제 로직은 app/services/customer_interest.py, 고객 CRUD·소개서
파일은 app/services/customer_management.py."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel

from app.db import engine
from app.deps import require_auth
from app.services import audit
from app.services.customer_eligibility import EligibilityDraft, get_eligibility_profile, save_eligibility_profile
from app.services.customer_interest import (
    InterestDraft,
    draft_from_profile,
    get_interest_profile,
    list_customers,
    save_interest_profile,
    top_matches,
)
from app.services.recommendation_signals import ALL_SIGNALS, ALL_SIGNAL_VARIANTS, PROFILE_PRESETS, score_with_profile
from app.services.customer_management import (
    CustomerDraft,
    EmailScheduleError,
    add_document,
    create_customer,
    delete_customer,
    delete_document,
    get_customer,
    get_document,
    list_customers_full,
    list_documents,
    set_email_schedule,
    update_customer,
)
from app.services.customer_profile import (
    LLMNotConfiguredError as ProfileLLMNotConfiguredError,
    MODEL_ALIASES as MODEL_ALIASES_PROFILE,
    NoDocumentsError,
    save_manual_profile_summary,
    summarize_customer_profile,
)
from app.services.interest_report import REPORT_LIMIT, delete_report, generate_report, list_reports, send_report_email
from app.services.mailer import SmtpNotConfiguredError
from app.services.report_commentary import (
    LLMNotConfiguredError as CommentaryLLMNotConfiguredError,
    MODEL_ALIASES as MODEL_ALIASES_COMMENTARY,
    NoProfileError,
    ReportNotFoundError,
    generate_report_commentary,
)

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("")
def get_customers(_email: str = Depends(require_auth)) -> list[dict]:
    with engine.connect() as conn:
        return list_customers(conn)


class CustomerPayload(BaseModel):
    name: str
    plan_tier: str = "standard"
    contact_email: str | None = None
    contact_name: str | None = None
    contact_title: str | None = None
    contact_phone: str | None = None
    report_recipient_emails: list[str] = []
    reference_urls: list[str] = []
    active: bool = True

    def to_draft(self) -> CustomerDraft:
        return CustomerDraft(**self.model_dump())


@router.get("/full")
def get_customers_full(_email: str = Depends(require_auth)) -> list[dict]:
    """고객 관리 화면용 — 담당자·보고서 수신자 등 전체 필드. 드롭다운용 가벼운 목록은
    위 GET /customers(list_customers)를 그대로 둔다(관심주제 화면이 이미 그걸 씀)."""
    with engine.connect() as conn:
        return list_customers_full(conn)


@router.post("", status_code=status.HTTP_201_CREATED)
def post_customer(payload: CustomerPayload, _email: str = Depends(require_auth)) -> dict:
    with engine.begin() as conn:
        customer_id = create_customer(conn, payload.to_draft())
    return {"id": customer_id}


@router.patch("/{customer_id}")
def patch_customer(customer_id: int, payload: CustomerPayload, _email: str = Depends(require_auth)) -> dict:
    with engine.begin() as conn:
        found = update_customer(conn, customer_id, payload.to_draft())
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
    return {"id": customer_id}


class EmailScheduleEntry(BaseModel):
    day: int
    time: str


class EmailSchedulePayload(BaseModel):
    schedule: list[EmailScheduleEntry] = []


@router.patch("/{customer_id}/email-schedule")
def patch_email_schedule(
    customer_id: int, payload: EmailSchedulePayload, email: str = Depends(require_auth)
) -> dict:
    """보고서 메일 자동발송 (요일,시각) 쌍(2026-09-14 도입, 2026-09-15 요일마다 다른 시각을
    지정할 수 있도록 재설계 — "월 13시, 목 14시"처럼) — app/scheduler.py의
    run_due_customer_emails가 이 값을 그대로 읽어 실제 발송을 실행한다
    (app/services/customer_management.py의 set_email_schedule/validate_email_schedule 참고)."""
    schedule = [entry.model_dump() for entry in payload.schedule]
    with engine.begin() as conn:
        try:
            found = set_email_schedule(conn, customer_id, schedule)
        except EmailScheduleError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
        audit.record(
            conn, actor=email, action="customer.email_schedule", target_type="customer", target_id=customer_id,
            detail={"schedule": schedule},
        )
    return {"id": customer_id, "schedule": schedule}


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_customer_route(customer_id: int, _email: str = Depends(require_auth)) -> None:
    with engine.begin() as conn:
        try:
            found = delete_customer(conn, customer_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")


# ---- 소개서 파일(다중 업로드) ------------------------------------------------------


@router.get("/{customer_id}/documents")
def get_documents(customer_id: int, _email: str = Depends(require_auth)) -> list[dict]:
    with engine.connect() as conn:
        if get_customer(conn, customer_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
        return list_documents(conn, customer_id)


@router.post("/{customer_id}/documents", status_code=status.HTTP_201_CREATED)
async def post_documents(
    customer_id: int, files: list[UploadFile] = File(...), email: str = Depends(require_auth)
) -> dict:
    """여러 파일 중 하나가 크기 초과 등으로 실패해도 나머지는 그대로 저장한다(2026-09-11
    수정) — 예전엔 파일 하나만 실패해도 예외가 트랜잭션 전체를 롤백시켜, 정상 파일도 같이
    안 올라간 채 "업로드는 끝난 것 같은데 파일이 안 보인다"로 이어졌다. 실패한 파일은
    errors에 사유와 함께 그대로 보고한다 — 조용히 건너뛰지 않는다."""
    with engine.begin() as conn:
        if get_customer(conn, customer_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
        errors: list[str] = []
        uploaded_count = 0
        for f in files:
            content = await f.read()
            try:
                add_document(
                    conn, customer_id, filename=f.filename or "제목없음", content_type=f.content_type,
                    content=content, uploaded_by=email,
                )
                uploaded_count += 1
            except ValueError as exc:
                errors.append(str(exc))
        if errors and uploaded_count == 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=" / ".join(errors))
        return {"documents": list_documents(conn, customer_id), "errors": errors}


@router.get("/{customer_id}/documents/{document_id}/download")
def download_document(customer_id: int, document_id: int, _email: str = Depends(require_auth)) -> Response:
    with engine.connect() as conn:
        doc = get_document(conn, customer_id, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="파일을 찾을 수 없습니다.")
    # HTTP 헤더는 latin-1만 허용돼서 한글 파일명은 RFC 5987(filename*=UTF-8''...)로 인코딩해야
    # 한다 — 일반 filename=""도 같이 줘서(ASCII로 안전하게 대체) 옛 클라이언트 호환.
    encoded_name = quote(doc["filename"])
    return Response(
        content=doc["content"],
        media_type=doc["content_type"] or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=\"document\"; filename*=UTF-8''{encoded_name}"},
    )


@router.delete("/{customer_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_document_route(customer_id: int, document_id: int, _email: str = Depends(require_auth)) -> None:
    with engine.begin() as conn:
        found = delete_document(conn, customer_id, document_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="파일을 찾을 수 없습니다.")


class InterestPayload(BaseModel):
    topic_ids: list[int] = []
    topic_priorities: dict[int, str] = {}  # topic_id -> high/normal/low, 없으면 normal
    terms: list[str] = []
    followed_org_ids: list[int] = []
    price_min: int | None = None  # 관심 공고 추천 금액 하한(2026-09-07), 없으면 필터 없음
    # 관심 사업유형 선호(2026-09-21, 의사결정_로그 192번) — {사업유형: "positive"/"negative"},
    # 지정 안 한 사업유형은 중립.
    work_type_prefs: dict[str, str] = {}

    def to_draft(self) -> InterestDraft:
        return InterestDraft(
            topic_ids=self.topic_ids,
            topic_priorities=self.topic_priorities,
            terms=self.terms,
            followed_org_ids=self.followed_org_ids,
            price_min=self.price_min,
            work_type_prefs=self.work_type_prefs,
        )


@router.get("/{customer_id}/interests")
def get_interests(customer_id: int, _email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        profile = get_interest_profile(conn, customer_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
    return profile


@router.put("/{customer_id}/interests", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def put_interests(customer_id: int, payload: InterestPayload, _email: str = Depends(require_auth)) -> None:
    with engine.begin() as conn:
        if get_interest_profile(conn, customer_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
        try:
            save_interest_profile(conn, customer_id, payload.to_draft())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


class EligibilityProfilePayload(BaseModel):
    company_size_tier: str | None = None
    has_research_institute: bool | None = None
    venture_cert: bool | None = None
    industry_codes: list[str] = []
    certifications: list[str] = []

    def to_draft(self) -> EligibilityDraft:
        return EligibilityDraft(
            company_size_tier=self.company_size_tier,
            has_research_institute=self.has_research_institute,
            venture_cert=self.venture_cert,
            industry_codes=self.industry_codes,
            certifications=self.certifications,
        )


@router.get("/{customer_id}/eligibility-profile")
def get_eligibility_profile_route(customer_id: int, _email: str = Depends(require_auth)) -> dict:
    with engine.connect() as conn:
        profile = get_eligibility_profile(conn, customer_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
    return profile


@router.put("/{customer_id}/eligibility-profile", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def put_eligibility_profile_route(customer_id: int, payload: EligibilityProfilePayload, email: str = Depends(require_auth)) -> None:
    with engine.begin() as conn:
        if get_eligibility_profile(conn, customer_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
        try:
            save_eligibility_profile(conn, customer_id, payload.to_draft())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        audit.record(
            conn, actor=email, action="customer.eligibility_profile", target_type="customer", target_id=customer_id,
            detail=payload.model_dump(),
        )


@router.get("/{customer_id}/interest-matches/compare")
def get_interest_matches_compare(customer_id: int, _email: str = Depends(require_auth)) -> dict:
    """추천 다중 신호 비교 샌드박스(2026-09-16 신설, 2026-09-21 신호 여러 개를 껐다 켰다
    하며 비교하는 구조로 재설계 — 의사결정_로그 192·196번, MatchingComparisonPage.tsx 전용).
    맨 앞(key="live")은 top_matches()를 그대로 호출한 실제 발송 결과이고, 나머지는
    PROFILE_PRESETS에 등록된 이름별 신호 조합마다 규칙 매칭을 기준 축으로 삼아 재정렬한
    실험 결과다. **이 엔드포인트 자체는 조회만 하고 아무것도 저장하지 않는다** — 실제
    고객 리포트 발송(top_matches 호출부인 interest_report.py)에는 전혀 영향 없음."""
    with engine.connect() as conn:
        profile = get_interest_profile(conn, customer_id)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
        draft = draft_from_profile(profile)
        # 2026-09-21 사용자 지시 — "지금 실제 메일에 쓰이는 방식"을 맨 앞에 진짜 기준선으로
        # 넣어야 나머지 실험 프로필과 공정하게 비교된다. 비교 페이지의 "규칙 매칭" 프로필은
        # score_with_profile(min_score=0, 섹션 배분 없음)이라 top_matches()(min_score=30,
        # 사전규격/진행중 섹션 배분, 상한 REPORT_LIMIT)와 실제로 다르다 — 그 차이 자체가
        # 실측 없이는 안 보이므로, top_matches()를 그대로 호출해 별도 신호 없이 내려준다.
        live_matches = [{**m, "signals": {}} for m in top_matches(conn, draft, limit=REPORT_LIMIT)]
        profiles = [
            {
                "key": "live",
                "label": "현재 실제 발송 방식",
                "description": (
                    "지금 고객 리포트 이메일에 실제로 발송되는 것과 완전히 같은 함수(top_matches)를 그대로 호출한 결과입니다 — "
                    "규칙 매칭 점수 30점 이상만, 사전규격 10건+진행중 20건으로 자리를 나눠 배분하고 상한 30건. "
                    "아래 실험 프로필들과 비교할 진짜 기준선입니다."
                ),
                "matches": live_matches,
            },
            *[
                {
                    "key": key,
                    "label": preset["label"],
                    "description": preset["description"],
                    "matches": score_with_profile(
                        conn, draft, profile, customer_id=customer_id, enabled_signals=preset["signals"], limit=20
                    ),
                }
                for key, preset in PROFILE_PRESETS.items()
            ],
        ]
    return {"profiles": profiles}


@router.get("/{customer_id}/interest-matches/compare-all-signal-variants")
def get_interest_matches_compare_all_signal_variants(customer_id: int, _email: str = Depends(require_auth)) -> dict:
    """"전체 신호"(다섯 신호를 한꺼번에 결합) 결합 방식만 따로 실험하는 팝업 전용
    엔드포인트(2026-09-21, 의사결정_로그 198번) — 노이즈-OR이 신호 하나만 강해도 빠르게
    포화돼 다른 프로필과 결과가 너무 달라진다는 실측 지적에, 결합 방식 자체를 4가지로
    비교해본다(ALL_SIGNAL_VARIANTS 참고). 메인 비교 화면(compare)에서는 뺐다."""
    with engine.connect() as conn:
        profile = get_interest_profile(conn, customer_id)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
        draft = draft_from_profile(profile)
        profiles = [
            {
                "key": key,
                "label": variant["label"],
                "description": variant["description"],
                "matches": score_with_profile(
                    conn, draft, profile, customer_id=customer_id, enabled_signals=ALL_SIGNALS, limit=20,
                    weights=variant["weights"], combine_fn=variant["combine_fn"], signal_floor=variant["signal_floor"],
                ),
            }
            for key, variant in ALL_SIGNAL_VARIANTS.items()
        ]
    return {"profiles": profiles}


@router.post("/{customer_id}/reports", status_code=status.HTTP_201_CREATED)
def post_report(customer_id: int, _email: str = Depends(require_auth)) -> dict:
    report = generate_report(customer_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
    return report


@router.get("/{customer_id}/reports")
def get_reports(customer_id: int, _email: str = Depends(require_auth)) -> list[dict]:
    with engine.connect() as conn:
        return list_reports(conn, customer_id)


@router.delete("/{customer_id}/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_report_route(customer_id: int, report_id: int, _email: str = Depends(require_auth)) -> None:
    with engine.begin() as conn:
        found = delete_report(conn, customer_id, report_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="보고서를 찾을 수 없습니다.")


@router.post("/{customer_id}/reports/{report_id}/send")
def post_send_report(customer_id: int, report_id: int, _email: str = Depends(require_auth)) -> dict:
    """설정된 보고서 수신자 이메일로 즉시 발송한다(관리자가 누를 때만 — 자동 발송 아님)."""
    with engine.connect() as conn:
        try:
            return send_report_email(conn, customer_id, report_id)
        except ReportNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except SmtpNotConfiguredError as exc:
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


class ProfileSummarizeRequest(BaseModel):
    model: str = "sonnet"  # 프로필 요약은 1회성·저빈도라 기본을 sonnet으로(품질 우선)


@router.post("/{customer_id}/profile/summarize")
def post_profile_summarize(
    customer_id: int, payload: ProfileSummarizeRequest, _email: str = Depends(require_auth)
) -> dict:
    """고객 소개서 원문을 요약해 MD로 캐싱한다("B로 하자" 결정) — LLM 호출 비용이 발생하므로
    관리자가 명시적으로 눌렀을 때만 실행(자동 실행 금지, 원칙 3). 소개서를 새로 올려도
    자동 재요약하지 않으며, 이 버튼을 다시 눌러야 갱신된다."""
    model = MODEL_ALIASES_PROFILE.get(payload.model, payload.model)
    with engine.begin() as conn:
        if get_customer(conn, customer_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
        try:
            return summarize_customer_profile(conn, customer_id, model=model)
        except NoDocumentsError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except ProfileLLMNotConfiguredError as exc:
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


class ProfileSummaryEditRequest(BaseModel):
    summary_md: str


@router.patch("/{customer_id}/profile")
def patch_profile_summary(
    customer_id: int, payload: ProfileSummaryEditRequest, _email: str = Depends(require_auth)
) -> dict:
    """관리자가 AI 요약을 직접 다듬을 때(개조식 손질·오탈자 수정 등) — LLM을 다시 부르지
    않고 텍스트만 바꾼다. 이후 고객 전략 수립 단계에서 이 필드를 그대로 참고자료로 쓴다."""
    with engine.begin() as conn:
        if get_customer(conn, customer_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="고객을 찾을 수 없습니다.")
        save_manual_profile_summary(conn, customer_id, payload.summary_md)
    return {"summary_md": payload.summary_md}


class ReportCommentaryRequest(BaseModel):
    model: str = "sonnet"


@router.post("/{customer_id}/reports/{report_id}/ai-commentary")
def post_report_commentary(
    customer_id: int, report_id: int, payload: ReportCommentaryRequest, _email: str = Depends(require_auth)
) -> dict:
    """S8 원칙 1(선별은 규칙 기반)과 모순되지 않도록, 공고 선별 결과는 그대로 두고 "왜
    의미있는지" 코멘트만 LLM(Sonnet)이 덧붙인다. 고객 프로필 요약이 먼저 있어야 한다."""
    model = MODEL_ALIASES_COMMENTARY.get(payload.model, payload.model)
    with engine.begin() as conn:
        try:
            return generate_report_commentary(conn, report_id, model=model)
        except ReportNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except NoProfileError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except CommentaryLLMNotConfiguredError as exc:
            raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
