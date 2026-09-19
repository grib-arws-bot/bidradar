import { apiClient } from "@/api/client";

// S8 파일럿(A0+A1만, 2026-09-03) — 첨부문서 텍스트 추출까지만. LLM 판정(A2 이후)은 범위 밖.
export interface AnalysisDoc {
  name: string;
  kind: string; // pdf/hwpx/hwp/other
  extract_method: string | null;
  extract_ok: boolean;
  error: string | null;
  text: string | null;
}

export interface ExtractionResult {
  analysis_id: number;
  status: string; // running/done/failed
  step?: string;
  ver?: number;
  finished_at?: string | null;
  attachments_found?: number;
  docs: AnalysisDoc[];
  error?: string | null; // status가 failed일 때 사유(2026-09-06 — 조용히 실패하지 않도록 화면에 노출)
}

export async function fetchLatestExtraction(noticeId: number): Promise<ExtractionResult | null> {
  const { data } = await apiClient.get<ExtractionResult | null>(`/notices/${noticeId}/extract`);
  return data;
}

export async function runExtraction(noticeId: number): Promise<ExtractionResult> {
  const { data } = await apiClient.post<ExtractionResult>(`/notices/${noticeId}/extract`);
  return data;
}

// S8 A2(요구사양 구조화, LLM, 2026-09-05) — 판정(A3)은 아직 없다. judgement 필드가 없는 건
// 의도된 것 — "unknown"이라도 보이면 마치 충족 여부가 정해진 것처럼 오해를 줄 수 있어 백엔드
// 응답 자체에서 뺐다.
export interface Requirement {
  category: string;
  req_text: string;
  req_value: string | null;
  req_unit: string | null;
  op: "gte" | "lte" | "eq" | "contains" | "manual";
  cite: string;
  task_ref: string | null; // 성능 요구사항이 특정 과제(content_items[].title)에 속하면 그 title
}

export interface AnalysisEvaluationItem {
  item: string;
  weight: string;
  note?: string;
}

export interface AnalysisBudgetConditions {
  government_support_ratio: string;
  institution_cash_burden_ratio: string;
  tech_fee_collection: string;
  youth_hiring_requirement: string;
  labor_cost_basis: string;
}

export interface AnalysisTaskType {
  execution_system: string; // 추진체계
  development_form: string; // 개발형태
  call_type: string; // 공모형태
}

export interface AnalysisContact {
  department: string;
  role: string;
  phone: string;
  email: string;
}

export interface AnalysisContentItem {
  title: string;
  summary: string;
  period: string;
  budget: string;
  task_type: AnalysisTaskType; // 과제마다 추진체계/개발형태/공모형태가 다를 수 있음(2026-09-05)
  lead_org: string; // 이 과제만의 주관연구개발기관 제한(예: "비영리기관") — 참여 판단에 결정적일 수 있음
}

export interface AnalysisEligibility {
  consortium: string;
  lead_org: string;
  participant_org: string;
  demand_org: string;
  company_size: string;
  special_notes: string;
}

export interface AnalysisSubmission {
  deadline: string;
  method: string;
  documents: string[];
}

export interface AnalysisSummary {
  project_period: string;
  project_budget: string;
  purpose: string;
  sub_business: string;
  task_type: AnalysisTaskType;
  contact: AnalysisContact;
  content_items: AnalysisContentItem[];
  evaluation: AnalysisEvaluationItem[];
  budget_conditions: AnalysisBudgetConditions;
  eligibility: AnalysisEligibility;
  submission: AnalysisSubmission;
  other_notes: string;
}

export interface RequirementsResult {
  analysis_id: number;
  status: string;
  step: string | null;
  summary: AnalysisSummary | null;
  // true면 summary가 "진짜 최신 분석"이 아니라 그 이전에 AI분석까지 완료된 버전에서 가져온
  // 값이다 — 첨부문서만 다시 추출(재추출)하고 아직 AI분석은 안 돌린 상태(2026-09-13).
  summary_outdated: boolean;
  requirements: Requirement[];
}

export type LlmModel = "haiku" | "sonnet" | "opus";

export async function fetchRequirements(noticeId: number): Promise<RequirementsResult | null> {
  const { data } = await apiClient.get<RequirementsResult | null>(`/notices/${noticeId}/requirements`);
  return data;
}

export async function runStructuring(noticeId: number, model: LlmModel): Promise<{ saved: number; cost_usd: number }> {
  const { data } = await apiClient.post(`/notices/${noticeId}/structure`, { model });
  return data;
}

// 사내 sLLM(A, extract-requirements) 요구사항 추출 미리보기(2026-09-20) — A2(Haiku) 실행 전
// 무료로 먼저 훑어보는 용도. analysis_requirement(A2 확정 결과)와 별개이며 판정 근거로 쓰지
// 않는다 — "확인 필요" 미리보기로만 노출한다.
export interface SllmRequirementPreview {
  status: "queued" | "running" | "done" | "failed";
  chunks_processed: number | null;
  chunks_total: number | null;
  requirements: Requirement[] | null;
  rejected_ungrounded_count: number | null;
  duplicate_count: number | null;
  error: string | null;
}

export async function startSllmRequirementPreview(noticeId: number): Promise<SllmRequirementPreview> {
  const { data } = await apiClient.post<SllmRequirementPreview>(`/notices/${noticeId}/sllm-requirements`);
  return data;
}

export async function fetchSllmRequirementPreview(noticeId: number): Promise<SllmRequirementPreview | null> {
  const { data } = await apiClient.get<SllmRequirementPreview | null>(`/notices/${noticeId}/sllm-requirements`);
  return data;
}
