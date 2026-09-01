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
