import { CircularProgress, CssBaseline, ThemeProvider } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import { ToastProvider } from "@/components/ToastProvider";
import { DashboardLayout } from "@/layouts/DashboardLayout";
import { AgencyChannelDetailPage } from "@/pages/AgencyChannelDetailPage";
import { AgencyStatusPage } from "@/pages/AgencyStatusPage";
import { CustomerDetailPage } from "@/pages/CustomerDetailPage";
import { CustomersPage } from "@/pages/CustomersPage";
import { DataChannelsPage } from "@/pages/DataChannelsPage";
import { LoginPage } from "@/pages/LoginPage";
import { NoticeDetailPage } from "@/pages/NoticeDetailPage";
import { NoticeExplorePage } from "@/pages/NoticeExplorePage";
import { OverviewPage } from "@/pages/OverviewPage";
import { PublicNoticeDetailPage } from "@/pages/PublicNoticeDetailPage";
import { PublicReportPage } from "@/pages/PublicReportPage";
import { PublicReportSourcesPage } from "@/pages/PublicReportSourcesPage";
import { ReportsManagementPage } from "@/pages/ReportsManagementPage";
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
      <Route path="/r/:token/sources" element={<PublicReportSourcesPage />} />
      <Route path="/r/:token/notices/:noticeId" element={<PublicNoticeDetailPage />} />
      {/* "AI 사업 추진 전략"은 2026-09-12부터 별도 페이지가 아니라 공고 상세 페이지 하단
          섹션으로 통합됨 — 예전 링크(북마크 등)는 그 공고 상세로 되돌린다. */}
      <Route path="/r/:token/notices/:noticeId/strategy" element={<Navigate to=".." replace />} />
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
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/customers/reports" element={<ReportsManagementPage />} />
        <Route path="/customers/:id" element={<CustomerDetailPage />} />
        <Route path="/admin/channels" element={<DataChannelsPage />} />
        <Route path="/admin/agencies" element={<AgencyStatusPage />} />
        <Route path="/admin/agencies/:sourceId" element={<AgencyChannelDetailPage />} />
        <Route path="/admin/topics" element={<TopicsPage />} />
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
        <ToastProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
