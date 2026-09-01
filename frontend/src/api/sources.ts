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
