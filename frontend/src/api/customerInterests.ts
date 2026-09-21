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
  // 관심 사업유형(2026-09-21, 의사결정_로그 192번) — work_types 카탈로그(고정값) 중 선택.
  work_type_ids: string[];
}

export interface InterestProfile extends InterestDraft {
  customer_id: number;
  customer_name: string;
  topics: { id: number; name: string }[];
  // 사업유형 고정 카탈로그(개발/연구/구매/구축/물품/용역/유지보수/운영/고도화) — 화면
  // 체크리스트용. interest_topic처럼 관리자가 편집하는 카탈로그가 아니라 코드에 고정된 값.
  work_types: string[];
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

// 추천 다중 신호 비교 샌드박스(2026-09-16 신설, 2026-09-21 신호를 이름별로 껐다 켰다
// 하는 구조로 재설계 — 의사결정_로그 192번, MatchingComparisonPage.tsx 전용). 규칙 매칭을
// 대체하는 게 아니라 여러 신호 조합이 실제로 얼마나 다르게 추천하는지 비교 확인용.
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
  score: number;
}

export interface MatchProfile {
  key: string;
  label: string;
  matches: MatchItem[];
}

export interface InterestMatchesCompare {
  profiles: MatchProfile[];
}

export async function fetchInterestMatchesCompare(customerId: number): Promise<InterestMatchesCompare> {
  const { data } = await apiClient.get<InterestMatchesCompare>(`/customers/${customerId}/interest-matches/compare`);
  return data;
}
