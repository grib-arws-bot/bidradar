import { Box, Card, Chip, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { Link as RouterLink } from "react-router-dom";

import { fetchOverview } from "@/api/overview";

const STATUS_LABEL: Record<string, { label: string; color: "success" | "warning" | "error" | "default" }> = {
  ok: { label: "정상", color: "success" },
  warn: { label: "주의", color: "warning" },
  fail: { label: "실패", color: "error" },
  inactive: { label: "비활성", color: "default" },
  no_run_yet: { label: "수집 전", color: "default" },
};

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <Card variant="outlined" sx={{ p: 2.5, flex: 1, minWidth: 160 }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h2" className="tnum">
        {value}
      </Typography>
      {sub && (
        <Typography variant="caption" color="text.secondary">
          {sub}
        </Typography>
      )}
    </Card>
  );
}

// "전체 시스템 운영을 위한 관리자 페이지"(2026-09-01 요청) — 로그인 후 첫 화면.
export function OverviewPage() {
  const { data, isLoading } = useQuery({ queryKey: ["overview"], queryFn: fetchOverview });

  if (isLoading || !data) {
    return <Typography>불러오는 중...</Typography>;
  }

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h2">전체 현황</Typography>
        <Typography variant="body2" color="text.secondary">
          공고 탐색으로 가기 전에, 시스템이 지금 어떻게 돌아가고 있는지 한눈에.
        </Typography>
      </Box>

      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        <StatCard label="전체 공고" value={data.notices.total} sub={`최근 24시간 +${data.notices.added_24h}`} />
        <StatCard label="지난 7일 신규" value={data.notices.added_7d} />
        <StatCard label="고객" value={data.customers.total} sub={`관심주제 설정 ${data.customers.with_interests}곳`} />
        <StatCard
          label="소스"
          value={data.sources.sources.length}
          sub={`정상 ${data.sources.counts.ok ?? 0} · 주의 ${data.sources.counts.warn ?? 0} · 실패 ${data.sources.counts.fail ?? 0}`}
        />
      </Stack>

      <Card variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h3" sx={{ mb: 1.5 }}>
          소스 상태
        </Typography>
        <Stack spacing={1}>
          {data.sources.sources.map((s) => {
            const meta = STATUS_LABEL[s.status] ?? STATUS_LABEL.no_run_yet;
            return (
              <Stack key={s.id} direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="body2">{s.name}</Typography>
                <Stack direction="row" spacing={1.5} alignItems="center">
                  <Typography variant="caption" color="text.secondary">
                    {s.last_run_at ? new Date(s.last_run_at).toLocaleString("ko-KR") : "수집 이력 없음"}
                  </Typography>
                  <Chip label={meta.label} size="small" color={meta.color} />
                </Stack>
              </Stack>
            );
          })}
        </Stack>
      </Card>

      <Card variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h3" sx={{ mb: 1.5 }}>
          최근 생성된 리포트
        </Typography>
        <Stack spacing={1}>
          {data.recent_reports.map((r) => (
            <Stack key={r.id} direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="body2">
                {r.customer_name} · {new Date(r.generated_at).toLocaleString("ko-KR")}
              </Typography>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <Typography variant="caption" color="text.secondary">
                  조회 {r.view_count}회
                </Typography>
                <RouterLink to={`/r/${r.token}`} target="_blank" rel="noreferrer">
                  <Typography variant="caption" color="primary.main">
                    미리보기 →
                  </Typography>
                </RouterLink>
              </Stack>
            </Stack>
          ))}
          {data.recent_reports.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              아직 생성된 리포트가 없습니다. 고객 관심 주제 화면에서 만들 수 있습니다.
            </Typography>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}
