import { apiClient } from "@/api/client";

export interface Me {
  email: string;
}

export async function fetchMe(): Promise<Me> {
  const { data } = await apiClient.get<Me>("/auth/me");
  return data;
}

export async function login(email: string, password: string, remember: boolean): Promise<Me> {
  const { data } = await apiClient.post<Me>("/auth/login", { email, password, remember });
  return data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/auth/logout");
}

export async function checkDevAutologinEnabled(): Promise<boolean> {
  const { data } = await apiClient.get<{ status: string; dev_autologin_enabled: boolean }>("/health");
  return data.dev_autologin_enabled;
}

// 로컬 개발 전용 — 백엔드가 ENABLE_DEV_AUTOLOGIN=true일 때만 응답한다(404 아니면 성공).
// stg(docker-compose 로컬 기동)는 기본 꺼져 있어 prod와 동일하게 로그인 절차를 거친다.
export async function devAutologin(): Promise<Me> {
  const { data } = await apiClient.post<Me>("/auth/dev-autologin");
  return data;
}
