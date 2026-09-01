import { Box, Card, Chip, Stack, Typography } from "@mui/material";

import type { NoticeItem } from "@/api/notices";

function formatPrice(value: number | null): string {
  if (value === null) return "미공개";
  const eok = value / 100_000_000;
  return eok >= 1 ? `${eok.toFixed(1)}억원` : `${(value / 10_000).toFixed(0)}만원`;
}

function formatDday(closeDt: string | null): { label: string; urgent: boolean } | null {
  if (!closeDt) return null;
  const diffMs = new Date(closeDt).getTime() - Date.now();
  const days = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  if (days < 0) return { label: "마감", urgent: false };
  return { label: days === 0 ? "D-Day" : `D-${days}`, urgent: days <= 3 };
}

export function NoticeCard({ notice, highlight }: { notice: NoticeItem; highlight?: string }) {
  const dday = formatDday(notice.close_dt);

  return (
    <Card variant="outlined" sx={{ p: 2.5 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
        <Box sx={{ minWidth: 0 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
            <Chip label={notice.stage} size="small" color="secondary" variant="outlined" />
            {notice.assignee_name && <Chip label={`담당: ${notice.assignee_name}`} size="small" />}
          </Stack>
          <Typography variant="h3" sx={{ mb: 0.5 }}>
            <HighlightedText text={notice.title} highlight={highlight} />
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {notice.org_name ?? "발주기관 미상"}
            {notice.region ? ` · ${notice.region}` : ""}
          </Typography>
        </Box>
        <Stack alignItems="flex-end" spacing={0.5} sx={{ flexShrink: 0 }}>
          <Typography variant="body2" className="tnum" fontWeight={600}>
            {formatPrice(notice.est_price)}
          </Typography>
          {dday && (
            <Chip
              label={dday.label}
              size="small"
              color={dday.urgent ? "error" : "default"}
              variant={dday.urgent ? "filled" : "outlined"}
            />
          )}
        </Stack>
      </Stack>
    </Card>
  );
}

function HighlightedText({ text, highlight }: { text: string; highlight?: string }) {
  if (!highlight) return <>{text}</>;
  const index = text.toLowerCase().indexOf(highlight.toLowerCase());
  if (index === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <Box component="mark" sx={{ bgcolor: "primary.lighter", color: "primary.darker", px: 0.25 }}>
        {text.slice(index, index + highlight.length)}
      </Box>
      {text.slice(index + highlight.length)}
    </>
  );
}
