import { apiClient } from "@/api/client";
import type { BidStatus } from "@/api/notices";

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

// 규칙 매칭·코사인 유사도 매칭 비교(2026-09-16, MatchingComparisonPage.tsx 전용) — 규칙
// 매칭을 대체하는 게 아니라 두 방식이 실제로 얼마나 다르게 추천하는지 비교 확인용.
export interface MatchItem {
  id: number;
  notice_no: string | null;
  title: string;
  stage: string;
  org_name: string | null;
  est_price: number | null;
  region: string | null;
  open_dt: string | null;
  close_dt: string | null;
  notice_type: string;
  bid_status: BidStatus;
  notice_status_label: string;
  work_type_label: string;
  topics: string[];
  score?: number; // 규칙 매칭(rule_based)에만 있음
  cosine_score?: number; // 코사인 매칭(cosine)에만 있음 — 규칙 점수와 척도가 다름
}

export interface InterestMatchesCompare {
  rule_based: MatchItem[];
  cosine: MatchItem[];
  // 후보 공고 중 아직 임베딩이 없는 건수(배치가 10분마다 채워나감) — 0이 아니면 코사인
  // 결과가 아직 불완전할 수 있다는 안내에 쓴다.
  pending_embeddings: number;
}

export async function fetchInterestMatchesCompare(customerId: number): Promise<InterestMatchesCompare> {
  const { data } = await apiClient.get<InterestMatchesCompare>(`/customers/${customerId}/interest-matches/compare`);
  return data;
}
