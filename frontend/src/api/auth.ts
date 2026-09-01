import { apiClient } from "@/api/client";

export interface Me {
  email: string;
}

export async function fetchMe(): Promise<Me> {
  const { data } = await apiClient.get<Me>("/auth/me");
  return data;
}

export async function login(email: string, password: string): Promise<Me> {
  const { data } = await apiClient.post<Me>("/auth/login", { email, password });
  return data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/auth/logout");
}

export async function checkIsDev(): Promise<boolean> {
  const { data } = await apiClient.get<{ status: string; is_dev: boolean }>("/health");
  return data.is_dev;
}

// 로컬 개발 전용 — 백엔드가 is_dev(ENVIRONMENT != "production")일 때만 응답한다(404 아니면 성공).
export async function devAutologin(): Promise<Me> {
  const { data } = await apiClient.post<Me>("/auth/dev-autologin");
  return data;
}
