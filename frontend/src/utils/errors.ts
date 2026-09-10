import type { AxiosError } from "axios";

// 백엔드가 HTTPException(detail=...)로 원인을 담아 보내면 그대로 꺼내 보여준다(CLAUDE.md
// "에러 메시지는 원인과 해결 방법을 함께" 원칙) — 없으면 fallback만 보여준다.
export function apiErrorMessage(error: unknown, fallback = "요청 처리 중 오류가 발생했습니다."): string {
  const detail = (error as AxiosError<{ detail?: string }>)?.response?.data?.detail;
  return detail || fallback;
}
