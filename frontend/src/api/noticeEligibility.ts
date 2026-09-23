import { apiClient } from "@/api/client";

// 공고별 자격요건 판정(2026-09-23) — app/services/analysis/eligibility.py의 규칙 비교
// 결과. judgement는 "ok"(충족)/"no"(미충족)/"unknown"(확인 필요, 애매하면 항상 이 값).
export interface EligibilityAxisVerdict {
  judgement: "ok" | "no" | "unknown";
  reason: string;
  cite: string | null;
}

export interface EligibilityVerdict {
  overall: "ok" | "no" | "unknown";
  axes: Record<string, EligibilityAxisVerdict>;
}

export const ELIGIBILITY_AXIS_LABELS: Record<string, string> = {
  company_size: "기업규모",
  research_institute: "연구소 보유",
  venture_cert: "벤처기업 인증",
  industry_codes: "업종",
  certifications: "기타 인증",
};

export async function fetchNoticeEligibility(noticeId: number, customerId: number): Promise<EligibilityVerdict | null> {
  const { data } = await apiClient.get<EligibilityVerdict | null>(`/notices/${noticeId}/eligibility`, {
    params: { customer_id: customerId },
  });
  return data;
}
