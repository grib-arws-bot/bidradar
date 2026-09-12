import { Card, Chip, Grid, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import Chart from "react-apexcharts";

import { fetchNoticeOverview, fetchSystemOverview } from "@/api/overview";

const STATUS_LABEL: Record<string, { label: string; color: "success" | "warning" | "error" | "default" }> = {
  ok: { label: "정상", color: "success" },
  warn: { label: "주의", color: "warning" },
  fail: { label: "실패", color: "error" },
  inactive: { label: "비활성", color: "default" },
  no_run_yet: { label: "수집 전", color: "default" },
};

const LINE_COLORS = ["#1a73e8", "#66bb6a", "#f4511e", "#8e24aa", "#00897b", "#fbc02d"];

function monthDayLabel(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${Number(m)}/${Number(d)}`;
}

// 카드 3: 공고 데이터(2026-09-12 재설계 — 사용자 지시 "매일매일의 변화 추세를 선그래프로") —
// 왼쪽은 전체 소스 누적 총량의 일별 추이(선 1개), 오른쪽은 소스별 일별 신규 수집 건수(선
// 여러 개) — 분석상태(미분석/첨부완료/AI완료) 구분은 값 차이가 너무 커서 의미가 없다는
// 피드백으로 뺐다. 데이터 수집채널 상태도 같은 지시로 이 카드 안(하단)에 병합했다 — API는
// 시스템 현황과 같은 쿼리 키("overview-system")를 그대로 재사용.
export function NoticeOverviewCard() {
  const { data, isLoading } = useQuery({ queryKey: ["overview-notices"], queryFn: fetchNoticeOverview });
  const { data: systemData } = useQuery({ queryKey: ["overview-system"], queryFn: fetchSystemOverview });

  if (isLoading || !data) {
    return (
      <Card sx={{ p: 3 }}>
        <Typography variant="body2" color="text.secondary">
          불러오는 중...
        </Typography>
      </Card>
    );
  }

  const cumulativeCategories = data.cumulative_daily.map((d) => monthDayLabel(d.date));
  const collectedCategories = data.collected_daily.dates.map(monthDayLabel);

  return (
    <Card sx={{ p: 3 }}>
      <Typography variant="h3" sx={{ mb: 2 }}>
        공고 데이터
      </Typography>
      <Grid container spacing={4}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            누적 데이터(일별, 전체 소스 합산)
          </Typography>
          <Chart
            type="line"
            height={260}
            options={{
              chart: { toolbar: { show: false } },
              xaxis: { categories: cumulativeCategories },
              yaxis: { labels: { formatter: (v: number) => v.toFixed(0) } },
              stroke: { width: 3, curve: "smooth" },
              dataLabels: { enabled: false },
              colors: ["#1a73e8"],
              grid: { padding: { left: 8, right: 8 } },
            }}
            series={[{ name: "누적 건수", data: data.cumulative_daily.map((d) => d.total) }]}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            수집 데이터(일별, 소스별)
          </Typography>
          <Chart
            type="line"
            height={260}
            options={{
              chart: { toolbar: { show: false } },
              xaxis: { categories: collectedCategories },
              yaxis: { labels: { formatter: (v: number) => v.toFixed(0) } },
              stroke: { width: 2, curve: "smooth" },
              dataLabels: { enabled: false },
              colors: LINE_COLORS,
              legend: { position: "bottom" },
              grid: { padding: { left: 8, right: 8 } },
            }}
            series={data.collected_daily.series.map((s) => ({ name: s.source_name, data: s.counts }))}
          />
        </Grid>
      </Grid>

      {systemData && (
        <>
          <Typography variant="subtitle2" sx={{ mt: 3, mb: 1 }}>
            데이터 수집채널 상태
          </Typography>
          <Stack spacing={0.75}>
            {systemData.channels.map((c) => {
              const meta = STATUS_LABEL[c.status] ?? STATUS_LABEL.no_run_yet;
              return (
                <Stack key={c.id} direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2" noWrap sx={{ minWidth: 0 }}>
                    {c.name}
                  </Typography>
                  <Stack direction="row" spacing={1.5} alignItems="center" flexShrink={0}>
                    <Typography variant="caption" color="text.secondary">
                      {c.last_run_at ? new Date(c.last_run_at).toLocaleString("ko-KR") : "수집 이력 없음"}
                    </Typography>
                    <Chip label={meta.label} size="small" color={meta.color} />
                  </Stack>
                </Stack>
              );
            })}
          </Stack>
        </>
      )}
    </Card>
  );
}
