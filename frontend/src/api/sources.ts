import { apiClient } from "@/api/client";

export interface SourceRow {
  id: number;
  name: string;
  org_name: string | null;
  homepage_url: string | null;
  adapter_type: string;
  adapter_label: string;
  stage: string;
  // "running"(2026-09-08) — 이 소스의 수집이 서버에서 실제로 진행 중이다(수동/자동 무관).
  // 프론트가 새로고침·다른 탭이어도 "지금 수집" 버튼을 비활성화할 수 있게 서버가 준다.
  status: "ok" | "warn" | "fail" | "inactive" | "no_run_yet" | "running";
  last_run_at: string | null;
  legal_tier: "A" | "B" | "C";
  legal_verified_at: string | null;
  compliance_overdue: boolean;
  auto_extract: boolean;
  auto_analyze: boolean;
  active: boolean;
  notice_type: "공공입찰" | "정부지원";
  // 공고 업데이트 시간(2026-09-05) — 최대 3개, "HH:MM", 일부만 설정 가능. 설정 UI만이고
  // 실제 자동 실행 엔진은 아직 없다.
  schedule_times: string[];
}

export async function fetchSources(): Promise<SourceRow[]> {
  const { data } = await apiClient.get<SourceRow[]>("/admin/sources");
  return data;
}

export async function updateAutoExtract(sourceId: number, enabled: boolean): Promise<void> {
  await apiClient.patch(`/admin/sources/${sourceId}/auto-extract`, { auto_extract: enabled });
}

export async function updateActive(sourceId: number, enabled: boolean): Promise<void> {
  await apiClient.patch(`/admin/sources/${sourceId}/active`, { active: enabled });
}

export async function updateAutoAnalyze(sourceId: number, enabled: boolean): Promise<void> {
  await apiClient.patch(`/admin/sources/${sourceId}/auto-analyze`, { auto_analyze: enabled });
}

export async function updateScheduleTimes(sourceId: number, times: string[]): Promise<void> {
  await apiClient.patch(`/admin/sources/${sourceId}/schedule`, { schedule_times: times });
}

export interface CollectNowResult {
  id: number;
  fetched: number;
  inserted: number;
  skipped: number;
  scored: number;
  out_of_window: number;
  already_closed: number;
  dedup_groups_with_duplicates: number;
  dedup_notices_updated: number;
  // 첨부분석(A1)·AI분석(A2)까지 한 번에 이어진다(2026-09-07) — 소스의 auto_extract/
  // auto_analyze 설정을 따르므로 꺼져 있으면 대상(candidates)이 0건일 뿐이다.
  extraction_candidates: number;
  auto_extracted: number;
  analyze_candidates: number;
  auto_analyzed: number;
}

// 관리자가 스케줄과 무관하게 임의 시점에 즉시 1회 수집(2026-09-07). 실제 외부 API 호출이라
// 몇십 초 이상(첨부분석·AI분석까지 이어지면 더) 걸리거나 실패할 수 있다 — 호출부가 로딩
// 상태·에러를 반드시 화면에 보여줘야 함.
export async function collectNow(sourceId: number): Promise<CollectNowResult> {
  const { data } = await apiClient.post<CollectNowResult>(`/admin/sources/${sourceId}/collect-now`);
  return data;
}

export type AgencyStatus = "ok" | "warn" | "fail" | "inactive" | "no_run_yet" | "no_source" | "running";

export interface AgencyRow {
  id: number;
  name: string;
  abbr: string | null;
  category: string | null;
  channel_url: string | null;
  channel: string | null;
  adapter_label: string | null;
  status: AgencyStatus;
  last_run_at: string | null;
  // 준법 확인 배지(advisory INBOX #6) — channel(source)이 없으면 전부 null/false.
  legal_tier: "A" | "B" | "C" | null;
  legal_verified_at: string | null;
  compliance_overdue: boolean;
}

export interface AgencyFilters {
  q?: string;
  status?: AgencyStatus;
  category?: string;
  page?: number;
  size?: number;
}

export interface AgencyPage {
  items: AgencyRow[];
  total: number;
  page: number;
  size: number;
}

export async function fetchAgencies(filters: AgencyFilters = {}): Promise<AgencyPage> {
  const { data } = await apiClient.get<AgencyPage>("/admin/sources/agencies", { params: filters });
  return data;
}

export async function fetchAgencyCategories(): Promise<string[]> {
  const { data } = await apiClient.get<string[]>("/admin/sources/agencies/categories");
  return data;
}
