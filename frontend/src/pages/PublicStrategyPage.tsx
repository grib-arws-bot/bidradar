import ArrowBackIcon from "@mui/icons-material/ArrowBackOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import { Alert, Box, Button, Card, Chip, CircularProgress, Divider, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { Link as RouterLink, useParams } from "react-router-dom";

import { generatePublicNoticeStrategy } from "@/api/reports";
import Logo from "@/components/Logo";
import { MarkdownContent } from "@/components/MarkdownContent";

// "AI 사업 추진 전략" — 처음 열 때만 실제로 생성되고(멱등, app/services/notice_strategy.py),
// 그 안에서 필요하면 첨부문서 자동분석(A1)·AI분석(A2)까지 먼저 끝내므로 최초 조회는 다소
// 걸릴 수 있다. status가 "pending"(다른 요청이 이미 생성 중)이면 짧게 다시 확인한다 —
// 매번 새로 생성을 트리거하는 게 아니라 캐시된 결과만 폴링하는 것이라 여러 번 호출해도
// LLM 호출이 늘어나지 않는다.
export function PublicStrategyPage() {
  const { token, noticeId } = useParams<{ token: string; noticeId: string }>();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["public-notice-strategy", token, noticeId],
    queryFn: () => generatePublicNoticeStrategy(token!, Number(noticeId)),
    retry: false,
    refetchInterval: (query) => (query.state.data?.status === "pending" ? 3000 : false),
  });

  const backLink = `/r/${token}/notices/${noticeId}`;

  return (
    <Box
      sx={{
        minHeight: "100vh",
        py: { xs: 3, md: 6 },
        background: (theme) =>
          `linear-gradient(180deg, ${theme.palette.primary.main}0d 0%, ${theme.palette.background.default} 320px)`,
      }}
    >
      <Stack spacing={2.5} sx={{ maxWidth: 800, mx: "auto", px: 2 }}>
        <Logo size={34} />
        <Button component={RouterLink} to={backLink} startIcon={<ArrowBackIcon />} sx={{ alignSelf: "flex-start" }}>
          공고로 돌아가기
        </Button>

        <Card sx={{ p: { xs: 2.5, md: 4 }, borderRadius: 3, boxShadow: "0 8px 32px -12px rgba(0,0,0,0.15)" }}>
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 0.5 }}>
            <Box
              sx={{
                display: "grid",
                placeItems: "center",
                width: 40,
                height: 40,
                borderRadius: 2,
                bgcolor: "primary.lighter",
                color: "primary.main",
                flexShrink: 0,
              }}
            >
              <AutoAwesomeOutlinedIcon />
            </Box>
            <Typography variant="h2">AI 사업 추진 전략</Typography>
          </Stack>
          {data?.status === "done" && (
            <Chip label="AI 생성 참고자료" size="small" color="primary" variant="outlined" sx={{ mb: 1 }} />
          )}
          <Divider sx={{ my: 2 }} />

          {(isLoading || data?.status === "pending") && (
            <Stack alignItems="center" spacing={2} sx={{ py: 8 }}>
              <CircularProgress size={36} />
              <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
                처음 열람하는 공고라 AI가 분석 중입니다 — 최대 1분 정도 걸릴 수 있습니다.
                <br />
                이 페이지를 나가지 않아도 자동으로 갱신됩니다.
              </Typography>
            </Stack>
          )}

          {isError && (
            <Stack spacing={2} sx={{ py: 3 }}>
              <Alert severity="error">
                {(error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
                  "전략 생성에 실패했습니다."}
              </Alert>
              <Button variant="outlined" onClick={() => refetch()} sx={{ alignSelf: "flex-start" }}>
                다시 시도
              </Button>
            </Stack>
          )}

          {data?.status === "done" && data.strategy_md && <MarkdownContent>{data.strategy_md}</MarkdownContent>}
        </Card>

        <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
          이 내용은 검토를 돕는 참고자료이며, 참여 여부에 대한 최종 판단은 별도로 필요합니다.
        </Typography>
      </Stack>
    </Box>
  );
}
