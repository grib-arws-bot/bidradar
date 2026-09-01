import { apiClient } from "@/api/client";

export interface CustomerSummary {
  id: number;
  name: string;
  plan_tier: "internal" | "standard" | "premium";
}

export interface InterestDraft {
  topic_ids: number[];
  terms: string[];
  followed_org_ids: number[];
  price_min: number | null;
  price_max: number | null;
  regions: string[];
}

export interface InterestProfile extends InterestDraft {
  customer_id: number;
  customer_name: string;
  topics: { id: number; name: string }[];
}

export interface PreviewResult {
  count: number;
  samples: {
    id: number;
    title: string;
    stage: string;
    org_name: string | null;
    est_price: number | null;
    close_dt: string | null;
    score: number;
  }[];
  term_counts: Record<string, number>;
}

export interface SavedSearch {
  id: number;
  name: string;
  query_params: Record<string, unknown>;
  created_at: string;
}

export async function fetchCustomers(): Promise<CustomerSummary[]> {
  const { data } = await apiClient.get<CustomerSummary[]>("/customers");
  return data;
}

export async function fetchInterestProfile(customerId: number): Promise<InterestProfile> {
  const { data } = await apiClient.get<InterestProfile>(`/customers/${customerId}/interests`);
  return data;
}

export async function saveInterestProfile(customerId: number, draft: InterestDraft): Promise<void> {
  await apiClient.put(`/customers/${customerId}/interests`, draft);
}

export async function previewInterestProfile(customerId: number, draft: InterestDraft): Promise<PreviewResult> {
  const { data } = await apiClient.post<PreviewResult>(`/customers/${customerId}/interests/preview`, draft);
  return data;
}

export async function fetchSavedSearches(customerId: number): Promise<SavedSearch[]> {
  const { data } = await apiClient.get<SavedSearch[]>(`/customers/${customerId}/searches`);
  return data;
}

export async function deleteSavedSearch(customerId: number, searchId: number): Promise<void> {
  await apiClient.delete(`/customers/${customerId}/searches/${searchId}`);
}
