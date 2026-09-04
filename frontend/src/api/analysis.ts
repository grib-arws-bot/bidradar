import { apiClient } from "@/api/client";

// S8 파일럿(A0+A1만, 2026-09-03) — 첨부문서 텍스트 추출까지만. LLM 판정(A2 이후)은 범위 밖.
export interface AnalysisDoc {
  name: string;
  kind: string; // pdf/hwpx/hwp/other
  extract_method: string | null;
  extract_ok: boolean;
  error: string | null;
  text: string | null;
}

export interface ExtractionResult {
  analysis_id: number;
  status: string; // running/done/failed
  step?: string;
  ver?: number;
  finished_at?: string | null;
  attachments_found?: number;
  docs: AnalysisDoc[];
}

export async function fetchLatestExtraction(noticeId: number): Promise<ExtractionResult | null> {
  const { data } = await apiClient.get<ExtractionResult | null>(`/notices/${noticeId}/extract`);
  return data;
}

export async function runExtraction(noticeId: number): Promise<ExtractionResult> {
  const { data } = await apiClient.post<ExtractionResult>(`/notices/${noticeId}/extract`);
  return data;
}
