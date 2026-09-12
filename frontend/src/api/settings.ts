import { apiClient } from "@/api/client";

// 범용 앱 설정(2026-09-12) — 첫 항목은 보고서 자동 삭제 보관기간. 설정이 늘어나도 이
// 인터페이스에 필드만 추가하면 된다(app/services/app_settings.py 참고).
export interface AppSettings {
  report_retention_days: number | null;
}

export async function fetchSettings(): Promise<AppSettings> {
  const { data } = await apiClient.get<AppSettings>("/settings");
  return data;
}

export async function updateSettings(patch: Partial<AppSettings>): Promise<AppSettings> {
  const { data } = await apiClient.put<AppSettings>("/settings", patch);
  return data;
}
