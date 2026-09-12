import { Card, Grid, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import Chart from "react-apexcharts";

import { fetchNoticeOverview, type NoticeSourceBreakdown } from "@/api/overview";

const SERIES_COLORS = ["#9e9e9e", "#42a5f5", "#2e7d32"]; // 미분석 / 첨부분석완료 / AI분석완료

function toSourceSeries(rows: NoticeSourceBreakdown[]) {
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

function monthDayLabel(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${Number(m)}/${Number(d)}`;
}

// 카드 3: 공고 데이터(2026-09-12 재설계) — 왼쪽은 소스별 누적 현황(가로 스택 막대), 오른쪽은
// 최근 14일 일별 수집 추이(시계열 — 사용자 지시 "매일매일의 변화를 볼 수 있게"). 시계열은
// 전체 소스를 합산한 3계열(미분석/첨부분석완료/AI분석완료) 스택 막대로 — 소스별로 나누면
// 계열이 너무 많아져 하루 단위 변화가 오히려 안 보인다.
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

  const cumulativeTotal = data.cumulative.reduce((sum, r) => sum + r.total, 0);
  const { categories: sourceCategories, series: sourceSeries } = toSourceSeries(data.cumulative);
  const dailyCategories = data.daily.map((d) => monthDayLabel(d.date));

  return (
    <Card sx={{ p: 3 }}>
      <Typography variant="h3" sx={{ mb: 2 }}>
        공고 데이터
      </Typography>
      <Grid container spacing={4}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            누적 데이터(현재 기준) — 전체 {cumulativeTotal}건
          </Typography>
          {data.cumulative.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              데이터가 없습니다.
            </Typography>
          ) : (
            <Chart
              type="bar"
              height={Math.max(180, sourceCategories.length * 46)}
              options={{
                chart: { toolbar: { show: false }, stacked: true },
                plotOptions: { bar: { horizontal: true, barHeight: "60%" } },
                xaxis: { categories: sourceCategories },
                dataLabels: { enabled: false },
                colors: SERIES_COLORS,
                legend: { position: "bottom" },
                grid: { padding: { left: 8, right: 8 } },
              }}
              series={sourceSeries}
            />
          )}
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="baseline">
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              최근 14일 일별 수집 추이(전체 소스 합산)
            </Typography>
          </Stack>
          <Chart
            type="bar"
            height={280}
            options={{
              chart: { toolbar: { show: false }, stacked: true },
              plotOptions: { bar: { columnWidth: "65%" } },
              xaxis: { categories: dailyCategories },
              yaxis: { labels: { formatter: (v: number) => v.toFixed(0) } },
              dataLabels: { enabled: false },
              colors: SERIES_COLORS,
              legend: { position: "bottom" },
              grid: { padding: { left: 8, right: 8 } },
            }}
            series={[
              { name: "미분석", data: data.daily.map((d) => d.unanalyzed) },
              { name: "첨부분석완료", data: data.daily.map((d) => d.extracted_only) },
              { name: "AI분석완료", data: data.daily.map((d) => d.ai_analyzed) },
            ]}
          />
        </Grid>
      </Grid>
    </Card>
  );
}
