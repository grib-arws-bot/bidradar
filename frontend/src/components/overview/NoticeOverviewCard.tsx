import { Box, Card, Chip, Grid, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import Chart from "react-apexcharts";

import { fetchNoticeOverview, fetchSystemOverview, type ChannelStatus, type NoticeDailyChart } from "@/api/overview";

const STATUS_LABEL: Record<string, { label: string; color: "success" | "warning" | "error" | "default" }> = {
  ok: { label: "정상", color: "success" },
  warn: { label: "주의", color: "warning" },
  fail: { label: "실패", color: "error" },
  inactive: { label: "비활성", color: "default" },
  no_run_yet: { label: "수집 전", color: "default" },
};

const SOURCE_LINE_COLORS = ["#1a73e8", "#66bb6a", "#f4511e", "#8e24aa", "#00897b", "#fbc02d"];
const TOTAL_LINE_COLOR = "#212121";

function monthDayLabel(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${Number(m)}/${Number(d)}`;
}

function colorForIndex(i: number): string {
  return SOURCE_LINE_COLORS[i % SOURCE_LINE_COLORS.length];
}

function Dot({ color }: { color: string }) {
  return <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: color, flexShrink: 0 }} />;
}

// "전체" 합산 계열(source_id === null)만 검정 굵은 선으로 구분하고, 나머지 소스별 계열은
// 얇은 색선으로 — 소스 수가 늘어도 안전하게 색을 순환한다. 범례는 그래프 자체가 아니라
// 옆의 "데이터 수집채널" 카드가 대신한다(2026-09-12 사용자 지시).
function DailyLineChart({ title, chart }: { title: string; chart: NoticeDailyChart }) {
  const categories = chart.dates.map(monthDayLabel);
  const perSourceCount = chart.series.length - 1;
  const colors = [...Array.from({ length: perSourceCount }, (_, i) => colorForIndex(i)), TOTAL_LINE_COLOR];
  const widths = [...Array(perSourceCount).fill(2), 4];

  return (
    <Grid size={{ xs: 12, md: 4 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {title}
      </Typography>
      <Chart
        type="line"
        height={280}
        options={{
          chart: { toolbar: { show: false } },
          xaxis: { categories },
          yaxis: { labels: { formatter: (v: number) => v.toFixed(0) } },
          stroke: { width: widths, curve: "smooth" },
          dataLabels: { enabled: false },
          colors,
          legend: { show: false },
          grid: { padding: { left: 8, right: 8 } },
        }}
        series={chart.series.map((s) => ({ name: s.source_name, data: s.counts }))}
      />
    </Grid>
  );
}

// 그래프 범례를 겸하는 "데이터 수집채널" 목록 — 소스 순서를 collected_daily.series(그래프가
// 실제로 그리는 순서)와 맞춰서 점 색을 매핑한다(채널 목록·그래프 계열이 다른 조회라 소스
// 구성이 완전히 일치하지 않을 수 있어, 못 찾으면 회색으로 표시).
function ChannelLegend({ channels, sourceOrder }: { channels: ChannelStatus[]; sourceOrder: number[] }) {
  return (
    <Grid size={{ xs: 12, md: 4 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        데이터 수집채널
      </Typography>
      <Stack spacing={1}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Dot color={TOTAL_LINE_COLOR} />
          <Typography variant="body2" fontWeight={600}>
            전체
          </Typography>
        </Stack>
        {channels.map((c) => {
          const meta = STATUS_LABEL[c.status] ?? STATUS_LABEL.no_run_yet;
          const idx = sourceOrder.indexOf(c.id);
          const color = idx >= 0 ? colorForIndex(idx) : "#bdbdbd";
          return (
            <Stack key={c.id} direction="row" alignItems="center" spacing={1}>
              <Dot color={color} />
              <Stack sx={{ minWidth: 0, flex: 1 }}>
                <Typography variant="body2" noWrap>
                  {c.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {c.last_run_at ? new Date(c.last_run_at).toLocaleString("ko-KR") : "수집 이력 없음"}
                </Typography>
              </Stack>
              <Chip label={meta.label} size="small" color={meta.color} sx={{ flexShrink: 0 }} />
            </Stack>
          );
        })}
      </Stack>
    </Grid>
  );
}

// 카드 3: 공고 데이터(2026-09-12 재설계 — 사용자 지시 "매일매일의 변화 추세를 선그래프로",
// "소스별과 전체소스를 그려줘", "데이터 수집채널을 그래프 범례로 겸하게, 셋을 가로로 배치") —
// 데이터 수집채널·누적 데이터·수집 데이터를 한 줄에 나란히 놓는다. 분석상태(미분석/첨부완료/
// AI완료) 구분은 값 차이가 너무 커서 의미가 없다는 피드백으로 뺐다. 채널 데이터는 시스템
// 현황과 같은 쿼리 키("overview-system")를 그대로 재사용.
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

  const sourceOrder = data.collected_daily.series
    .filter((s) => s.source_id !== null)
    .map((s) => s.source_id as number);

  return (
    <Card sx={{ p: 3 }}>
      <Typography variant="h3" sx={{ mb: 2 }}>
        공고 데이터
      </Typography>
      <Grid container spacing={4}>
        {systemData && <ChannelLegend channels={systemData.channels} sourceOrder={sourceOrder} />}
        <DailyLineChart title="누적 데이터(일별, 소스별+전체, 삭제 데이터 제외)" chart={data.cumulative_daily} />
        <DailyLineChart title="수집 데이터(일별, 소스별+전체)" chart={data.collected_daily} />
      </Grid>
    </Card>
  );
}
