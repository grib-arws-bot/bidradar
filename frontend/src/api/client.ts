import axios from "axios";

// 브라우저는 항상 상대경로 /api만 호출한다 — nginx가 백엔드로 리버스 프록시하므로
// CORS 설정 자체가 필요 없다(CLAUDE.md "CORS 설정 추가 금지").
export const apiClient = axios.create({
  baseURL: "/api",
  withCredentials: true,
});

// 세션 만료를 즉시 감지해 로그인 화면으로 보낸다(2026-09-08 사용자 발견) — RequireAuth
// (App.tsx)는 대시보드 레이아웃을 감싸는 부모 라우트라 메뉴 이동(자식 라우트 전환)에서는
// 다시 마운트되지 않는다. 그 결과 useSession의 캐시(staleTime 5분)가 "로그인됨"으로 남은
// 채, 실제 세션은 만료돼 각 페이지의 데이터 조회만 401로 조용히 실패해 "틀만 있고 데이터
// 없음"으로 보이고, 사용자가 새로고침해야만(리액트 쿼리 캐시가 완전히 초기화되며 useSession이
// 다시 fetchMe를 부름) 로그인 화면으로 정상 전환됐다. 로그인 시도 자체의 401(비밀번호
// 오류)은 LoginPage가 폼 에러로 직접 처리해야 하므로 여기서 가로채지 않는다.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url: string = error?.config?.url ?? "";
    const isLoginAttempt = url.includes("/auth/login");
    if (status === 401 && !isLoginAttempt && window.location.pathname !== "/login") {
      window.location.assign("/login");
    }
    return Promise.reject(error);
  }
);
