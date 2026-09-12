import { Box, Card, Chip, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import Chart from "react-apexcharts";
import { Link as RouterLink } from "react-router-dom";

import { fetchCustomerOverview } from "@/api/overview";

function monthLabel(month: string): string {
  const [, m] = month.split("-");
  return `${Number(m)}월`;
}

// 카드 1: 고객 현황(2026-09-12 재설계) — 고객 수 누적 추이(선 그래프) + 보고서 생성/발송 수
// (막대 그래프), 최근 6개월. "기타 유용한 정보"로 관심주제·프로필요약 완료 수와 최근 리포트
// 목록(예전 4카드 버전에 있던 위젯)을 그대로 가져왔다.
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
        <Typography variant="h3">고객 현황</Typography>
        <Typography variant="h2" className="tnum">
          {data.total_customers}
        </Typography>
      </Stack>
      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        <Chip size="small" label={`관심주제 설정 ${data.with_interests}`} />
        <Chip size="small" label={`AI 프로필 요약 ${data.profile_summarized}`} />
      </Stack>

      <Typography variant="caption" color="text.secondary">
        고객 수 추이(누적)
      </Typography>
      <Chart
        type="line"
        height={140}
        options={{
          chart: { toolbar: { show: false }, sparkline: { enabled: false } },
          xaxis: { categories: months },
          yaxis: { labels: { formatter: (v: number) => v.toFixed(0) } },
          stroke: { width: 3, curve: "smooth" },
          dataLabels: { enabled: false },
          colors: ["#1a73e8"],
          grid: { padding: { left: 8, right: 8 } },
        }}
        series={[{ name: "고객 수", data: data.monthly.customer_total }]}
      />

      <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
        보고서 생성 · 발송 수(월별)
      </Typography>
      <Chart
        type="bar"
        height={160}
        options={{
          chart: { toolbar: { show: false }, stacked: false },
          xaxis: { categories: months },
          plotOptions: { bar: { columnWidth: "55%" } },
          dataLabels: { enabled: false },
          colors: ["#1a73e8", "#f4511e"],
          legend: { position: "bottom" },
          grid: { padding: { left: 8, right: 8 } },
        }}
        series={[
          { name: "생성", data: data.monthly.reports_generated },
          { name: "발송", data: data.monthly.reports_sent },
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
