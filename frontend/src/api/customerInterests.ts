import { apiClient } from "@/api/client";

export interface CustomerSummary {
  id: number;
  name: string;
  plan_tier: "internal" | "standard" | "premium";
}

export type TopicPriority = "high" | "normal" | "low";

export interface InterestDraft {
  topic_ids: number[];
  // topic_id(문자열 키, JSON 직렬화 특성) -> 우선순위. 없는 topic_id는 "normal" 취급(2026-09-05
  // — "관심주제로 선택만 하면 전부 동일 가중치"였던 걸 3단계로 세분화, 회사 핵심 사업 주제가
  // 부차적 관심사보다 항상 위로 오도록).
  topic_priorities: Record<string, TopicPriority>;
  terms: string[];
  followed_org_ids: number[];
  // 관심 공고 추천 금액 하한(2026-09-07) — 이 값 이상인 est_price를 가진 공고만 추천 대상.
  // null이면 필터 없음(미공개 est_price 공고는 하한이 걸려 있으면 항상 제외됨).
  price_min: number | null;
}

export interface InterestProfile extends InterestDraft {
  customer_id: number;
  customer_name: string;
  topics: { id: number; name: string }[];
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
