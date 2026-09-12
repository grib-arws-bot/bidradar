import { Card, Chip, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { fetchSystemOverview } from "@/api/overview";

const STATUS_LABEL: Record<string, { label: string; color: "success" | "warning" | "error" | "default" }> = {
  ok: { label: "정상", color: "success" },
  warn: { label: "주의", color: "warning" },
  fail: { label: "실패", color: "error" },
  inactive: { label: "비활성", color: "default" },
  no_run_yet: { label: "수집 전", color: "default" },
};

// 데이터 수집채널 상태(2026-09-12 재배치 — 원래 시스템 현황 카드 안에 있던 걸 별도 카드로
// 분리해 보고서 현황 카드 아래에 세로로 둔다, 사용자 지시). 데이터는 시스템 현황과 같은
// react-query 캐시 키("overview-system")를 그대로 재사용 — API를 새로 안 만들어도 된다.
export function ChannelStatusCard() {
  const { data, isLoading } = useQuery({ queryKey: ["overview-system"], queryFn: fetchSystemOverview });

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
      <Typography variant="h3" sx={{ mb: 1.5 }}>
        데이터 수집채널 상태
      </Typography>
      <Stack spacing={0.75}>
        {data.channels.map((c) => {
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
    </Card>
  );
}
