import { apiClient } from "@/api/client";

export type ClassificationAction = "confirm" | "recategorize" | "irrelevant";

export interface ClassificationPayload {
  action: ClassificationAction;
  categories?: number[];
  reason?: string;
}

export async function submitClassification(noticeId: number, payload: ClassificationPayload): Promise<void> {
  await apiClient.post(`/notices/${noticeId}/classification`, payload);
}

export async function followOrg(noticeId: number): Promise<void> {
  await apiClient.post(`/notices/${noticeId}/follow-org`);
}
