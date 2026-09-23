import { apiClient } from "@/api/client";

// 입찰 자격요건 검증(2026-09-23) — 고객사 자신의 자격 프로필. 공고 쪽 요구사항과 대조해
// 참여 가능 여부를 판정한다(app/services/analysis/eligibility.py). 이 값은 추천 점수에
// 절대 섞이지 않는다 — 별도 필터 전용.
export interface EligibilityDraft {
  company_size_tier: string | null;
  has_research_institute: boolean | null;
  venture_cert: boolean | null;
  industry_codes: string[];
  certifications: string[];
}

export interface EligibilityProfile extends EligibilityDraft {
  customer_id: number;
  customer_name: string;
  // 기업규모 고정 카탈로그("중소기업"/"중견기업"/"대기업") — work_types와 같은 패턴.
  company_size_tiers: string[];
}

export async function fetchEligibilityProfile(customerId: number): Promise<EligibilityProfile> {
  const { data } = await apiClient.get<EligibilityProfile>(`/customers/${customerId}/eligibility-profile`);
  return data;
}

export async function saveEligibilityProfile(customerId: number, draft: EligibilityDraft): Promise<void> {
  await apiClient.put(`/customers/${customerId}/eligibility-profile`, draft);
}
