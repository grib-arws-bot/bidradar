import { Card, Grid, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import Chart from "react-apexcharts";

import { fetchNoticeOverview, type NoticeSourceBreakdown } from "@/api/overview";

const SERIES_COLORS = ["#9e9e9e", "#42a5f5", "#2e7d32"]; // 미분석 / 첨부분석완료 / AI분석완료

function toSeries(rows: NoticeSourceBreakdown[]) {
  const categories = rows.map((r) => r.source_name);
  return {
    categories,
    series: [
      { name: "미분석", data: rows.map((r) => r.unanalyzed) },
      { name: "첨부분석완료", data: rows.map((r) => r.extracted_only) },
      { name: "AI분석완료", data: rows.map((r) => r.ai_analyzed) },
    ],
  };
}

function BreakdownChart({ title, rows }: { title: string; rows: NoticeSourceBreakdown[] }) {
  const { categories, series } = toSeries(rows);
  const total = rows.reduce((sum, r) => sum + r.total, 0);
  return (
    <Stack sx={{ flex: 1, minWidth: 0 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {title} — 전체 {total}건
      </Typography>
      {rows.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          데이터가 없습니다.
        </Typography>
      ) : (
        <Chart
          type="bar"
          height={Math.max(180, categories.length * 46)}
          options={{
            chart: { toolbar: { show: false }, stacked: true },
            plotOptions: { bar: { horizontal: true, barHeight: "60%" } },
            xaxis: { categories },
            dataLabels: { enabled: false },
            colors: SERIES_COLORS,
            legend: { position: "bottom" },
            grid: { padding: { left: 8, right: 8 } },
          }}
          series={series}
        />
      )}
    </Stack>
  );
}

// 카드 3: 공고 데이터(2026-09-12 재설계) — 누적 + 어제(KST) 수집분을 소스별로 미분석/
// 첨부분석완료/AI분석완료로 나눈 가로 스택 막대. 사용자 지시대로 그래프 2개로 분리했다.
export function NoticeOverviewCard() {
  const { data, isLoading } = useQuery({ queryKey: ["overview-notices"], queryFn: fetchNoticeOverview });

  if (isLoading || !data) {
    return (
      <Card sx={{ p: 3 }}>
        <Typography variant="body2" color="text.secondary">
          불러오는 중...
        </Typography>
      </Card>
    );
  }

  return (
    <Card sx={{ p: 3 }}>
      <Typography variant="h3" sx={{ mb: 2 }}>
        공고 데이터
      </Typography>
      <Grid container spacing={4}>
        <Grid size={{ xs: 12, md: 6 }}>
          <BreakdownChart title="누적 데이터(현재 기준)" rows={data.cumulative} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <BreakdownChart title={`전날 수집 데이터(${data.yesterday_date})`} rows={data.yesterday} />
        </Grid>
      </Grid>
    </Card>
  );
}
