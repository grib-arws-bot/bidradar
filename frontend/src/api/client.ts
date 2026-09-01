import axios from "axios";

// 브라우저는 항상 상대경로 /api만 호출한다 — nginx가 백엔드로 리버스 프록시하므로
// CORS 설정 자체가 필요 없다(CLAUDE.md "CORS 설정 추가 금지").
export const apiClient = axios.create({
  baseURL: "/api",
  withCredentials: true,
});
