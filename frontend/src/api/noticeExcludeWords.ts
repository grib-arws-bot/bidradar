import { apiClient } from "@/api/client";

// 공고 탐색 제목 제외 키워드(2026-09-13) — 관리 편의를 위해 그룹은 이 목록 하나뿐이다.
// keyword_rule(관심주제 L2 채점용)과는 완전히 별개 — 이건 순수 조회 시점 필터.
export interface NoticeExcludeWord {
  id: number;
  term: string;
}

export async function fetchNoticeExcludeWords(): Promise<NoticeExcludeWord[]> {
  const { data } = await apiClient.get<NoticeExcludeWord[]>("/admin/notice-exclude-words");
  return data;
}

export async function createNoticeExcludeWord(term: string): Promise<NoticeExcludeWord> {
  const { data } = await apiClient.post<NoticeExcludeWord>("/admin/notice-exclude-words", { term });
  return data;
}

export async function deleteNoticeExcludeWord(id: number): Promise<void> {
  await apiClient.delete(`/admin/notice-exclude-words/${id}`);
}
