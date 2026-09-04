import { apiClient } from "@/api/client";

export interface SourceRow {
  id: number;
  name: string;
  org_name: string | null;
  homepage_url: string | null;
  adapter_type: string;
  adapter_label: string;
  stage: string;
  status: "ok" | "warn" | "fail" | "inactive" | "no_run_yet";
  last_run_at: string | null;
  legal_tier: "A" | "B" | "C";
  legal_verified_at: string | null;
  compliance_overdue: boolean;
  auto_extract: boolean;
}

export async function fetchSources(): Promise<SourceRow[]> {
  const { data } = await apiClient.get<SourceRow[]>("/admin/sources");
  return data;
}

export async function updateAutoExtract(sourceId: number, enabled: boolean): Promise<void> {
  await apiClient.patch(`/admin/sources/${sourceId}/auto-extract`, { auto_extract: enabled });
}

export type AgencyStatus = "ok" | "warn" | "fail" | "inactive" | "no_run_yet" | "no_source";

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
