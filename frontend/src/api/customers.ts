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
  active: boolean;
  profile_summary_md: string | null;
  profile_summarized_at: string | null;
  profile_summary_cost: number;
}

export interface CustomerDraft {
  name: string;
  plan_tier: "internal" | "standard" | "premium";
  contact_email: string | null;
  contact_name: string | null;
  contact_title: string | null;
  contact_phone: string | null;
  report_recipient_emails: string[];
  active: boolean;
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

export async function uploadCustomerDocuments(customerId: number, files: File[]): Promise<CustomerDocument[]> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const { data } = await apiClient.post<CustomerDocument[]>(`/customers/${customerId}/documents`, form, {
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
