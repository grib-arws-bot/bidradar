import { apiClient } from "@/api/client";

export interface SourceHealth {
  id: number;
  name: string;
  status: "ok" | "warn" | "fail" | "inactive" | "no_run_yet";
  last_run_at: string | null;
}

export interface Overview {
  notices: {
    total: number;
    added_24h: number;
    added_7d: number;
    in_progress: number;
    closed: number;
  };
  customers: {
    total: number;
    with_interests: number;
    profile_summarized: number;
    by_tier: Record<string, number>;
  };
  reports: {
    total: number;
    added_7d: number;
    with_ai_commentary: number;
    total_views: number;
  };
  sources: {
    counts: Record<string, number>;
    sources: SourceHealth[];
    total: number;
    last_run_at: string | null;
  };
  pending_analysis: { extraction: number; analyze: number };
  recent_reports: {
    id: number;
    token: string;
    generated_at: string;
    view_count: number;
    customer_name: string;
  }[];
}

export async function fetchOverview(): Promise<Overview> {
  const { data } = await apiClient.get<Overview>("/overview");
  return data;
}
