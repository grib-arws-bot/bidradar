import type { ExtractionResult, RequirementsResult } from "@/api/analysis";
import { apiClient } from "@/api/client";
import type { BidStatus } from "@/api/notices";

export interface ReportNoticeItem {
  id: number;
  notice_no: string | null;
  title: string;
  stage: string;
  org_name: string | null;
  est_price: number | null;
  region: string | null;
  open_dt: string | null;
  close_dt: string | null;
  score: number;
  notice_type: string;
  bid_status: BidStatus;
  notice_status_label: string;
  work_type_label: string;
  // 이 공고가 왜 관심공고로 떴는지(어느 관심주제와 일치했는지, 2026-09-06 요청) — 구
  // 스냅샷(이 필드 도입 전)엔 없을 수 있어 옵셔널.
  topics?: string[];
  // AI 코멘트(2026-09-05) — 공고 선별은 규칙 기반 그대로, "왜 의미있는지"만 LLM이 덧붙인다.
  // 아직 생성 안 한 리포트엔 없을 수 있어 옵셔널.
  ai_commentary?: string;
  ai_strategy?: string;
}

export interface ReportSummary {
  total: number;
  closing_soon: number;
  top_score: number;
  // 리포트에 실제로 담긴 공고들의 출처표시 문구(advisory INBOX #7) — 생성 시점에 확정되어
  // 스냅샷에 고정된다. 구 스냅샷(이 필드 도입 전)엔 없을 수 있어 옵셔널.
  attributions?: string[];
}

export interface GeneratedReport {
  id: number;
  token: string;
  customer_id: number;
  notices: ReportNoticeItem[];
  summary: ReportSummary;
  generated_at: string;
}

export interface ReportListItem {
  id: number;
  token: string;
  generated_at: string;
  summary: ReportSummary;
  view_count: number;
  ai_generated_at: string | null;
}

export interface PublicReport {
  id: number;
  customer_id: number;
  customer_name: string;
  notices: ReportNoticeItem[];
  summary: ReportSummary;
  generated_at: string;
  view_count: number;
}

export async function generateReport(customerId: number): Promise<GeneratedReport> {
  const { data } = await apiClient.post<GeneratedReport>(`/customers/${customerId}/reports`);
  return data;
}

export async function fetchReports(customerId: number): Promise<ReportListItem[]> {
  const { data } = await apiClient.get<ReportListItem[]>(`/customers/${customerId}/reports`);
  return data;
}

export async function deleteReport(customerId: number, reportId: number): Promise<void> {
  await apiClient.delete(`/customers/${customerId}/reports/${reportId}`);
}

export interface SendReportResult {
  sent_to: string[];
}

// 설정된 보고서 수신자 이메일로 즉시 발송(2026-09-12) — 관리자가 누를 때만, 자동 발송 아님.
export async function sendReport(customerId: number, reportId: number): Promise<SendReportResult> {
  const { data } = await apiClient.post<SendReportResult>(`/customers/${customerId}/reports/${reportId}/send`);
  return data;
}

export async function fetchPublicReport(token: string): Promise<PublicReport> {
  const { data } = await apiClient.get<PublicReport>(`/public/reports/${token}`);
  return data;
}

// 공개 공고 상세 + "AI 사업 추진 전략"(2026-09-05) — 로그인 없이 리포트 토큰으로만 접근.
export interface PublicNoticeDetail {
  id: number;
  notice_no: string | null;
  title: string;
  stage: string;
  org_name: string | null;
  est_price: number | null;
  region: string | null;
  biz_type: string | null;
  open_dt: string | null;
  close_dt: string | null;
  url: string;
  notice_type: string;
  bid_status: BidStatus;
  notice_status_label: string;
  work_type_label: string;
  ai_summary: Record<string, unknown> | null;
  // 이미 생성된 "AI 사업 추진 전략"이 있으면(2026-09-12) 다시 "생성" 버튼을 보여주지 않고
  // 바로 그 내용을 보여주기 위함 — LLM을 다시 부르지 않는 조회 전용 필드.
  strategy: { status: "done"; strategy_md: string } | null;
}

export async function fetchPublicNotice(token: string, noticeId: number): Promise<PublicNoticeDetail> {
  const { data } = await apiClient.get<PublicNoticeDetail>(`/public/reports/${token}/notices/${noticeId}`);
  return data;
}

// 공고탐색(관리자)과 같은 상세 분석 탭·첨부원문을 리포트에도 보여주기 위함(2026-09-12) —
// AnalysisTabsSection·AnalyzedDocumentsSection이 그대로 재사용하는 타입이라 api/analysis.ts의
// RequirementsResult·ExtractionResult를 그대로 쓴다.
export async function fetchPublicRequirements(token: string, noticeId: number): Promise<RequirementsResult | null> {
  const { data } = await apiClient.get<RequirementsResult | null>(`/public/reports/${token}/notices/${noticeId}/requirements`);
  return data;
}

export async function fetchPublicExtraction(token: string, noticeId: number): Promise<ExtractionResult | null> {
  const { data } = await apiClient.get<ExtractionResult | null>(`/public/reports/${token}/notices/${noticeId}/extract`);
  return data;
}

export interface NoticeStrategyResult {
  status: "done" | "pending";
  strategy_md?: string;
  model?: string;
  cost_usd?: number;
}

// 처음 열 때만 실제로 생성되고, 몇 번을 다시 호출해도 캐시된 결과만 돌려준다(멱등) —
// 프론트는 그냥 이 함수를 다시 호출하는 것만으로 "생성 중" 폴링도 겸할 수 있다.
export async function generatePublicNoticeStrategy(token: string, noticeId: number): Promise<NoticeStrategyResult> {
  const { data } = await apiClient.post<NoticeStrategyResult>(`/public/reports/${token}/notices/${noticeId}/strategy`);
  return data;
}
