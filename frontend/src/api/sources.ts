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
}

export async function fetchSources(): Promise<SourceRow[]> {
  const { data } = await apiClient.get<SourceRow[]>("/admin/sources");
  return data;
}

export type AgencyStatus = "ok" | "warn" | "fail" | "inactive" | "no_run_yet" | "no_source";

export interface AgencyRow {
  id: number;
  name: string;
  abbr: string | null;
  category: string | null;
  notice_url: string | null;
  channel: string | null;
  adapter_label: string | null;
  status: AgencyStatus;
  last_run_at: string | null;
}

export interface AgencyFilters {
  q?: string;
  status?: AgencyStatus;
  category?: string;
}

export async function fetchAgencies(filters: AgencyFilters = {}): Promise<AgencyRow[]> {
  const { data } = await apiClient.get<AgencyRow[]>("/admin/sources/agencies", { params: filters });
  return data;
}
