import { Box, Stack, Typography } from "@mui/material";

import { CustomerOverviewCard } from "@/components/overview/CustomerOverviewCard";
import { NoticeOverviewCard } from "@/components/overview/NoticeOverviewCard";
import { SystemOverviewCard } from "@/components/overview/SystemOverviewCard";

// "전체 시스템 운영을 위한 관리자 페이지"(2026-09-01 요청) — 로그인 후 첫 화면.
// 3개 카드로 재구성(2026-09-12 요청): 보고서 현황·시스템 현황을 가로로, 공고 데이터(데이터
// 수집채널 상태 포함, 같은 날 재배치)를 그 아래 전체 폭으로. 각 카드는 자체 API를 쓰고
// (overview.ts) 독립적으로 로딩된다.
export function OverviewPage() {
  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h2">전체 현황</Typography>
        <Typography variant="body2" color="text.secondary">
          공고 탐색으로 가기 전에, 시스템이 지금 어떻게 돌아가고 있는지 한눈에.
        </Typography>
      </Box>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
          gap: 2,
          alignItems: "stretch",
        }}
      >
        <CustomerOverviewCard />
        <SystemOverviewCard />
      </Box>

      <NoticeOverviewCard />
    </Stack>
  );
}
