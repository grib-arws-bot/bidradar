import { Box, Card, Chip, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import Chart from "react-apexcharts";
import { Link as RouterLink } from "react-router-dom";

import { fetchCustomerOverview } from "@/api/overview";

function monthLabel(month: string): string {
  const [, m] = month.split("-");
  return `${Number(m)}월`;
}

// 카드 1: 보고서 현황(2026-09-12 재설계, "고객 현황"에서 개명 — 사용자 지시) — 고객 수 누적
// 추이(선)와 보고서 생성/발송 수(막대)를 별도 차트 2개 대신 혼합 차트 하나로 합쳤다(사용자
// 지시 "고객수 추이와 보고서 생성/발송을 하나의 그래프로 합쳐"). 고객 수는 절대값 스케일이
// 보고서 건수와 크게 달라 보조축(오른쪽)에 둔다.
export function CustomerOverviewCard() {
  const { data, isLoading } = useQuery({ queryKey: ["overview-customers"], queryFn: fetchCustomerOverview });

  if (isLoading || !data) {
    return (
      <Card sx={{ p: 3, height: "100%" }}>
        <Typography variant="body2" color="text.secondary">
          불러오는 중...
        </Typography>
      </Card>
    );
  }

  const months = data.monthly.months.map(monthLabel);

  return (
    <Card sx={{ p: 3, height: "100%" }}>
      <Stack direction="row" justifyContent="space-between" alignItems="baseline" sx={{ mb: 0.5 }}>
        <Typography variant="h3">보고서 현황</Typography>
        <Typography variant="h2" className="tnum">
          {data.total_customers}
        </Typography>
      </Stack>
      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        <Chip size="small" label={`관심주제 설정 ${data.with_interests}`} />
        <Chip size="small" label={`AI 프로필 요약 ${data.profile_summarized}`} />
      </Stack>

      <Typography variant="caption" color="text.secondary">
        고객 수(누적) · 보고서 생성/발송 수(월별)
      </Typography>
      <Chart
        type="line"
        height={260}
        options={{
          chart: { toolbar: { show: false } },
          xaxis: { categories: months },
          yaxis: [
            {
              seriesName: "고객 수",
              title: { text: "고객 수(누적)" },
              labels: { formatter: (v: number) => v.toFixed(0) },
            },
            {
              seriesName: "생성",
              opposite: true,
              title: { text: "보고서 건수" },
              labels: { formatter: (v: number) => v.toFixed(0) },
            },
            { seriesName: "발송", opposite: true, show: false },
          ],
          stroke: { width: [3, 0, 0], curve: "smooth" },
          plotOptions: { bar: { columnWidth: "45%" } },
          dataLabels: { enabled: false },
          colors: ["#1a73e8", "#66bb6a", "#f4511e"],
          legend: { position: "bottom" },
          grid: { padding: { left: 8, right: 8 } },
        }}
        series={[
          { name: "고객 수", type: "line", data: data.monthly.customer_total },
          { name: "생성", type: "column", data: data.monthly.reports_generated },
          { name: "발송", type: "column", data: data.monthly.reports_sent },
        ]}
      />

      <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>
        최근 생성된 리포트
      </Typography>
      <Stack spacing={0.75}>
        {data.recent_reports.map((r) => (
          <Stack key={r.id} direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="body2" noWrap sx={{ minWidth: 0 }}>
              {r.customer_name} · {new Date(r.generated_at).toLocaleDateString("ko-KR")}
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center" flexShrink={0}>
              <Typography variant="caption" color="text.secondary">
                조회 {r.view_count}회
              </Typography>
              <Box component={RouterLink} to={`/r/${r.token}`} target="_blank" rel="noreferrer">
                <Typography variant="caption" color="primary.main">
                  미리보기 →
                </Typography>
              </Box>
            </Stack>
          </Stack>
        ))}
        {data.recent_reports.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            아직 생성된 리포트가 없습니다.
          </Typography>
        )}
      </Stack>
    </Card>
  );
}
