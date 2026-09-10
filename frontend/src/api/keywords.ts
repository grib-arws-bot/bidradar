import { apiClient } from "@/api/client";

// 관심주제 키워드(L2 규칙, keyword_rule) 관리자 CRUD(2026-09-05 요청) — 지금까지는
// seed_constants.py 하드코딩값만 있었다.
export type WeightClass = "core" | "tech" | "ctx" | "block";

export interface Keyword {
  id: number;
  interest_topic_id: number;
  term: string;
  weight_class: WeightClass;
  weight: number;
  active: boolean;
}

export interface KeywordDraft {
  term: string;
  weight_class: WeightClass;
  weight: number;
}

export async function fetchKeywords(topicId: number): Promise<Keyword[]> {
  const { data } = await apiClient.get<Keyword[]>(`/admin/topics/${topicId}/keywords`);
  return data;
}

export async function createKeyword(topicId: number, draft: KeywordDraft): Promise<Keyword> {
  const { data } = await apiClient.post<Keyword>(`/admin/topics/${topicId}/keywords`, draft);
  return data;
}

export async function updateKeyword(keywordId: number, patch: Partial<KeywordDraft & { active: boolean }>): Promise<Keyword> {
  const { data } = await apiClient.patch<Keyword>(`/admin/topics/keywords/${keywordId}`, patch);
  return data;
}

export async function deleteKeyword(keywordId: number): Promise<void> {
  await apiClient.delete(`/admin/topics/keywords/${keywordId}`);
}

export interface RescanResult {
  scanned: number;
  added: number;
}

// 키워드를 추가·수정한 뒤 관리자가 눌러서 실행 — 이미 수집된 공고에도 새 규칙을 소급
// 적용한다(자동 실행 금지). 기존 매칭은 절대 건드리지 않고 새로 통과하는 조합만 추가.
export async function rescanKeywords(): Promise<RescanResult> {
  const { data } = await apiClient.post<RescanResult>("/admin/topics/keywords/rescan");
  return data;
}
