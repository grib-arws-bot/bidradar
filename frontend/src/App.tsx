import { CircularProgress, CssBaseline, ThemeProvider } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import { DashboardLayout } from "@/layouts/DashboardLayout";
import { ComingSoonPage } from "@/pages/ComingSoonPage";
import { CustomerInterestsPage } from "@/pages/CustomerInterestsPage";
import { LoginPage } from "@/pages/LoginPage";
import { NoticeDetailPage } from "@/pages/NoticeDetailPage";
import { NoticeExplorePage } from "@/pages/NoticeExplorePage";
import { OverviewPage } from "@/pages/OverviewPage";
import { PublicReportPage } from "@/pages/PublicReportPage";
import { SourcesPage } from "@/pages/SourcesPage";
import { TopicsPage } from "@/pages/TopicsPage";
import { useSession } from "@/hooks/useSession";
import { theme } from "@/theme";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

function RequireAuth({ children }: { children: ReactElement }) {
  const { data, isLoading, isError } = useSession();

  if (isLoading) {
    return (
      <div style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
        <CircularProgress />
      </div>
    );
  }
  if (isError || !data) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {/* 로그인 없는 외부 고객용 — 절대 RequireAuth/DashboardLayout 안에 넣지 말 것 */}
      <Route path="/r/:token" element={<PublicReportPage />} />
      <Route
        element={
          <RequireAuth>
            <DashboardLayout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<OverviewPage />} />
        <Route path="/notices" element={<NoticeExplorePage />} />
        <Route path="/notices/:id" element={<NoticeDetailPage />} />
        <Route path="/analyses" element={<ComingSoonPage title="심층 분석" />} />
        <Route path="/pipeline" element={<ComingSoonPage title="파이프라인" />} />
        <Route path="/orgs" element={<ComingSoonPage title="기관 프로파일" />} />
        <Route path="/analytics" element={<ComingSoonPage title="시장 분석" />} />
        <Route path="/customers/interests" element={<CustomerInterestsPage />} />
        <Route path="/admin/sources" element={<SourcesPage />} />
        <Route path="/admin/topics" element={<TopicsPage />} />
        <Route path="/admin/keywords" element={<ComingSoonPage title="키워드 사전" />} />
        <Route path="/admin/products" element={<ComingSoonPage title="제품 카탈로그" />} />
        <Route path="/admin/audit" element={<ComingSoonPage title="감사 로그" />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
