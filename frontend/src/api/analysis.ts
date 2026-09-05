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
  documents: string;
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
