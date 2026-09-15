import { apiClient } from "@/api/client";
import type { LlmModel } from "@/api/analysis";

// 고객 관리 CRUD(2026-09-05) — S7 관심주제(customerInterests.ts)와는 별개로 고객 "카드"
// 정보(담당자·보고서 수신자·소개서 파일)를 다룬다.
export interface CustomerFull {
  id: number;
  name: string;
  plan_tier: "internal" | "standard" | "premium";
  contact_email: string | null;
  contact_name: string | null;
  contact_title: string | null;
  contact_phone: string | null;
  report_recipient_emails: string[];
  reference_urls: string[];
  active: boolean;
  profile_summary_md: string | null;
  profile_summarized_at: string | null;
  profile_summary_cost: number;
  // 보고서 메일 자동발송 (요일,시각) 쌍(2026-09-14 도입, 2026-09-15 쌍으로 재설계 — "월
  // 13시, 목 14시"처럼 요일마다 다른 시각을 지정할 수 있어야 해서 days×times 조합에서
  // 바꿈). day는 ISO 요일 번호(1=월~7=일). 최대 3쌍(app/scheduler.py run_due_customer_emails).
  report_auto_send_schedule: EmailScheduleEntry[];
}

export interface EmailScheduleEntry {
  day: number;
  time: string;
}

export interface CustomerDraft {
  name: string;
  plan_tier: "internal" | "standard" | "premium";
  contact_email: string | null;
  contact_name: string | null;
  contact_title: string | null;
  contact_phone: string | null;
  report_recipient_emails: string[];
  reference_urls: string[];
  active: boolean;
}

// CustomerFull(서버 응답, 읽기 전용 필드 포함) -> CustomerDraft(PATCH 본문) 변환. 여러 화면이
// "지금 서버에 있는 값 그대로 + 필드 하나만 바꿔서" 저장해야 할 때 공용으로 쓴다(2026-09-15,
// CustomerEmailCard의 수신자 이메일 즉시저장 — CustomerDetailPage.tsx의 폼 draft와는 별개로
// 저장되므로, 그 draft를 거치지 않고 서버값 기준으로 직접 patch한다).
export function toCustomerDraft(c: CustomerFull): CustomerDraft {
  const {
    id: _id,
    profile_summary_md: _md,
    profile_summarized_at: _at,
    profile_summary_cost: _cost,
    report_auto_send_schedule: _schedule,
    ...draft
  } = c;
  return draft;
}

export async function fetchCustomersFull(): Promise<CustomerFull[]> {
  const { data } = await apiClient.get<CustomerFull[]>("/customers/full");
  return data;
}

export async function createCustomer(draft: CustomerDraft): Promise<{ id: number }> {
  const { data } = await apiClient.post<{ id: number }>("/customers", draft);
  return data;
}

export async function updateCustomer(id: number, draft: CustomerDraft): Promise<void> {
  await apiClient.patch(`/customers/${id}`, draft);
}

export async function deleteCustomer(id: number): Promise<void> {
  await apiClient.delete(`/customers/${id}`);
}

// 보고서 메일 자동발송 (요일,시각) 쌍 — 고객 정보 일괄저장(CustomerDraft)과 별개 엔드포인트
// (source.schedule_times와 같은 이유: 자동저장되는 별도 설정이라 "저장" 버튼과 묶지 않음).
export async function updateCustomerEmailSchedule(
  id: number,
  schedule: EmailScheduleEntry[],
): Promise<void> {
  await apiClient.patch(`/customers/${id}/email-schedule`, { schedule });
}

export interface CustomerDocument {
  id: number;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  uploaded_at: string;
  uploaded_by: string;
}

export async function fetchCustomerDocuments(customerId: number): Promise<CustomerDocument[]> {
  const { data } = await apiClient.get<CustomerDocument[]>(`/customers/${customerId}/documents`);
  return data;
}

export interface UploadDocumentsResult {
  documents: CustomerDocument[];
  errors: string[];
}

// 여러 파일 중 하나가 실패해도(예: 용량 초과) 나머지는 저장된다(2026-09-11) — 응답에 담긴
// errors를 호출부가 그대로 토스트로 보여줘야 한다("조용한 실패 금지").
export async function uploadCustomerDocuments(customerId: number, files: File[]): Promise<UploadDocumentsResult> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const { data } = await apiClient.post<UploadDocumentsResult>(`/customers/${customerId}/documents`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export function customerDocumentDownloadUrl(customerId: number, documentId: number): string {
  return `${apiClient.defaults.baseURL}/customers/${customerId}/documents/${documentId}/download`;
}

export async function deleteCustomerDocument(customerId: number, documentId: number): Promise<void> {
  await apiClient.delete(`/customers/${customerId}/documents/${documentId}`);
}

// 고객 프로필 요약("B로 하자" 결정, 2026-09-05) — 소개서 원문을 매번 LLM에 넣는 대신 한 번
// 요약해 캐싱한다. 재요약은 관리자가 이 버튼을 다시 눌러야만 일어난다(자동 실행 금지).
export interface ProfileSummarizeResult {
  summary_md: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  failed_urls: string[];
  auto_set_topics: string[];
}

export async function summarizeCustomerProfile(customerId: number, model: LlmModel): Promise<ProfileSummarizeResult> {
  const { data } = await apiClient.post<ProfileSummarizeResult>(`/customers/${customerId}/profile/summarize`, { model });
  return data;
}

// 관리자가 AI 요약을 직접 손질(개조식 다듬기 등)할 때 — LLM을 다시 부르지 않고 텍스트만 바꾼다.
export async function updateCustomerProfileSummary(customerId: number, summaryMd: string): Promise<void> {
  await apiClient.patch(`/customers/${customerId}/profile`, { summary_md: summaryMd });
}

export interface ReportCommentaryResult {
  annotated: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export async function generateReportCommentary(
  customerId: number,
  reportId: number,
  model: LlmModel,
): Promise<ReportCommentaryResult> {
  const { data } = await apiClient.post<ReportCommentaryResult>(
    `/customers/${customerId}/reports/${reportId}/ai-commentary`,
    { model },
  );
  return data;
}
