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
  // 관심 사업유형 선호(2026-09-21, 의사결정_로그 192번, 같은 날 +/중립/- 3단계로 확장) —
  // {사업유형: "positive"/"negative"}. 지정 안 한 사업유형(work_types 카탈로그에는 있지만
  // 이 맵에 키가 없는 것)은 중립 — 감리·구매처럼 "들어가면 오히려 감점해야 할" 유형을
  // negative로 지정할 수 있다.
  work_type_prefs: Record<string, "positive" | "negative">;
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
  // 2026-09-21 — 신호별 breakdown(의사결정_로그 192번 후속). 이 프로필에서 켠 신호 이름만
  // 키로 들어있고("rule"은 항상 포함), 값은 0~1 강도 또는 null(그 신호로는 평가 불가 —
  // 0점과 다름, 화면에서 구분해서 보여줘야 함).
  signals: Record<string, number | null>;
}

export interface MatchProfile {
  key: string;
  label: string;
  // 이 프로필이 어떤 입력을 보고 어떻게 계산하는지 — 컬럼 제목 바로 아래 그대로 노출한다.
  description: string;
  matches: MatchItem[];
}

export interface InterestMatchesCompare {
  profiles: MatchProfile[];
}

export async function fetchInterestMatchesCompare(customerId: number): Promise<InterestMatchesCompare> {
  const { data } = await apiClient.get<InterestMatchesCompare>(`/customers/${customerId}/interest-matches/compare`);
  return data;
}
