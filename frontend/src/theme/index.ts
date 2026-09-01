import { alpha, createTheme } from "@mui/material/styles";

// 출처: prototype/bidradar-prototype.html :root (구현스펙 05절 디자인 토큰). 값을 그대로 옮김 —
// 프로토타입이 바뀌면 여기도 같이 바꿔야 "테마가 프로토타입과 일치"가 계속 성립한다.
// 카드 그림자·칩 모양·보더 색은 2026-09-01 요청으로 ARWS(admin-page-v2) 스타일에 맞춤 —
// primary(주황 #DE5B21)만 유지하고, 점선 보더 대신 옅은 그림자 카드로 통일.
export const theme = createTheme({
  palette: {
    primary: {
      lighter: "#FFE9DC",
      light: "#FF9E6B",
      main: "#DE5B21",
      dark: "#B24314",
      darker: "#78290C",
      contrastText: "#FFFFFF",
    },
    secondary: {
      lighter: "#D8F1F0",
      light: "#4BB3B0",
      main: "#0B7A78",
      dark: "#065452",
      contrastText: "#FFFFFF",
    },
    success: { main: "#118D57" },
    warning: { main: "#B76E00" },
    error: { main: "#B71D18" },
    grey: {
      100: "#F9FAFB",
      200: "#F4F6F8",
      300: "#DFE3E8",
      400: "#C4CDD5",
      500: "#919EAB",
      600: "#637381",
      700: "#454F5B",
      800: "#212B36",
      900: "#161C24",
    },
    background: {
      default: "#F4F6F8",
      paper: "#FFFFFF",
    },
    text: {
      primary: "#212B36",
    },
  },
  shape: {
    borderRadius: 8, // 버튼 기준(--r-btn). 카드는 컴포넌트별로 16 오버라이드
  },
  typography: {
    fontFamily: '"DM Sans","Noto Sans KR",-apple-system,system-ui,sans-serif',
    fontSize: 14,
    h2: { fontSize: 24, fontWeight: 700 },
    h3: { fontSize: 15.5, fontWeight: 700 },
    body1: { fontSize: 14, lineHeight: 1.6 },
  },
  components: {
    MuiCard: {
      defaultProps: { variant: "elevation", elevation: 0 },
      styleOverrides: {
        root: ({ theme }) => ({
          borderRadius: 16,
          border: "none",
          boxShadow: `0 0 2px 0 ${alpha(theme.palette.grey[500], 0.2)}, 0 12px 24px -4px ${alpha(theme.palette.grey[500], 0.12)}`,
        }),
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: ({ theme }) => ({
          backgroundImage: "none",
          "&.MuiPaper-outlined": { borderColor: alpha(theme.palette.grey[500], 0.16) },
        }),
      },
    },
  },
});

declare module "@mui/material/styles" {
  interface PaletteColor {
    lighter?: string;
    darker?: string;
  }
  interface SimplePaletteColorOptions {
    lighter?: string;
    darker?: string;
  }
}
