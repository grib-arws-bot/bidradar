import ArrowBackIcon from "@mui/icons-material/ArrowBackOutlined";
import { Box, Button, Card, CircularProgress, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { Link as RouterLink, useParams } from "react-router-dom";

import { fetchPublicReport } from "@/api/reports";
import Logo from "@/components/Logo";

// 리포트 본문에 있던 출처표시를 별도 페이지로 분리(2026-09-07 사용자 지시) — 나라장터·IRIS뿐
// 아니라 소스가 계속 늘어날 예정이라, 본문에 매번 나열하는 대신 링크 하나로 뺐다. 이용약관·
// 개인정보처리방침은 아직 없음 — 나중에 필요해지면 이 페이지에 같이 추가하기로 함(2026-09-07
// 사용자 지시, 지금은 범위 밖).
export function PublicReportSourcesPage() {
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

  const attributions = data.summary.attributions ?? [];

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default", py: { xs: 3, md: 6 } }}>
      <Stack spacing={3} sx={{ maxWidth: 720, mx: "auto", px: 2 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Logo size={34} />
        </Stack>

        <Button component={RouterLink} to={`/r/${token}`} startIcon={<ArrowBackIcon />} sx={{ alignSelf: "flex-start" }}>
          리포트로 돌아가기
        </Button>

        <Card sx={{ p: 3 }}>
          <Typography variant="h2" sx={{ mb: 2 }}>
            데이터 출처
          </Typography>
          {attributions.length > 0 ? (
            <Stack spacing={1}>
              {attributions.map((text) => (
                <Typography key={text} variant="body2" color="text.secondary">
                  {text}
                </Typography>
              ))}
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">
              이 리포트에 담긴 공고의 출처 정보가 없습니다.
            </Typography>
          )}
        </Card>
      </Stack>
    </Box>
  );
}
