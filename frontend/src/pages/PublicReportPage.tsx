import { Box, Card, Chip, CircularProgress, Divider, Link, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { fetchPublicReport } from "@/api/reports";
import Logo from "@/components/Logo";

function formatPrice(value: number | null): string {
  if (value === null) return "미공개";
  return `${(value / 100_000_000).toFixed(1)}억원`;
}

// 로그인 없는 서명된 공유 링크(의사결정_로그 8·9번) — 외부 고객이 이메일의 "상세보기"를 눌러
// 도착하는 화면. DashboardLayout(사이드바·계정) 없이 이 페이지 하나만 독립적으로 보여준다.
export function PublicReportPage() {
  const { token } = useParams<{ token: string }>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["public-report", token],
    queryFn: () => fetchPublicReport(token!),
    retry: false,
  });

  if (isLoading) {
    return (
      <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (isError || !data) {
    return (
      <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <Typography>리포트를 찾을 수 없습니다. 링크가 만료되었을 수 있습니다.</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default", py: { xs: 3, md: 6 } }}>
      <Stack spacing={3} sx={{ maxWidth: 720, mx: "auto", px: 2 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Logo size={34} />
          <Chip label={data.customer_name} size="small" sx={{ ml: "auto" }} />
        </Stack>

        <Card sx={{ p: 3 }}>
          <Typography variant="h2">이번 주 관심 공고</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {new Date(data.generated_at).toLocaleDateString("ko-KR")} 기준 · 총 {data.summary.total}건
            {data.summary.closing_soon > 0 && ` · 7일 내 마감 ${data.summary.closing_soon}건`}
          </Typography>

          <Stack spacing={1.5}>
            {data.notices.map((n) => (
              <Box key={n.id} sx={{ p: 2, borderRadius: 2, bgcolor: "grey.100" }}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
                  <Box sx={{ minWidth: 0 }}>
                    <Chip label={n.stage} size="small" color="secondary" variant="outlined" sx={{ mb: 0.5 }} />
                    <Typography variant="body1" fontWeight={600}>
                      {n.title}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {n.org_name ?? "발주기관 미상"}
                    </Typography>
                  </Box>
                  <Stack alignItems="flex-end" sx={{ flexShrink: 0 }}>
                    <Typography variant="body2" className="tnum" fontWeight={600}>
                      {formatPrice(n.est_price)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {n.close_dt ? new Date(n.close_dt).toLocaleDateString("ko-KR") + " 마감" : "마감일 미상"}
                    </Typography>
                  </Stack>
                </Stack>
              </Box>
            ))}
            {data.notices.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                이번 주엔 관심 조건에 맞는 공고가 없었습니다.
              </Typography>
            )}
          </Stack>
        </Card>

        <Divider />
        {/* 출처표시(advisory INBOX #7) — 리포트에 실제로 담긴 공고의 출처만, 생성 시점에
            source.attribution_text에서 자동으로 가져와 스냅샷에 고정된다. 사람이 문구를
            골라 붙이는 게 아니라서 빠뜨릴 수가 없다. */}
        {(data.summary.attributions ?? []).map((text) => (
          <Typography key={text} variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
            {text}
          </Typography>
        ))}
        <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
          문의: <Link href="mailto:report@grib.co.kr">report@grib.co.kr</Link>
        </Typography>
      </Stack>
    </Box>
  );
}
