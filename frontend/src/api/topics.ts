import { apiClient } from "@/api/client";

export interface Topic {
  id: number;
  name: string;
  description: string | null;
  sort_order: number;
  active: boolean;
}

export interface TopicCreate {
  name: string;
  description?: string | null;
  sort_order?: number;
}

export interface TopicUpdate {
  name?: string;
  description?: string | null;
  sort_order?: number;
  active?: boolean;
}

export async function fetchTopics(): Promise<Topic[]> {
  const { data } = await apiClient.get<Topic[]>("/admin/topics");
  return data;
}

export async function createTopic(payload: TopicCreate): Promise<Topic> {
  const { data } = await apiClient.post<Topic>("/admin/topics", payload);
  return data;
}

export async function updateTopic(id: number, payload: TopicUpdate): Promise<Topic> {
  const { data } = await apiClient.patch<Topic>(`/admin/topics/${id}`, payload);
  return data;
}
