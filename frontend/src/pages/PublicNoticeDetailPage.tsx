import ArrowBackIcon from "@mui/icons-material/ArrowBackOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import FavoriteIcon from "@mui/icons-material/Favorite";
import FavoriteBorderOutlinedIcon from "@mui/icons-material/FavoriteBorderOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNewOutlined";
import { Alert, Box, Button, Card, Chip, CircularProgress, Divider, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";

import { BID_STATUS_LABELS } from "@/api/notices";
import {
  fetchPublicExtraction,
  fetchPublicNotice,
  fetchPublicRequirements,
  generatePublicNoticeStrategy,
  recordPublicNoticeView,
  setPublicNoticeLike,
  type PublicNoticeDetail,
} from "@/api/reports";
import { AnalysisTabsSection } from "@/components/notice-detail/AnalysisTabsSection";
import { AnalyzedDocumentsSection } from "@/components/notice-detail/AnalyzedDocumentsSection";
import Logo from "@/components/Logo";
import { MarkdownContent } from "@/components/MarkdownContent";
import { isAttachmentDownloadUrl } from "@/utils/noticeLinks";

function formatPrice(value: number | null): string {
  if (value === null) return "미공개";
  const eok = value / 100_000_000;
  return eok >= 1 ? `${eok.toFixed(1)}억원` : `${(value / 10_000).toFixed(0)}만원`;
}

function daysUntil(target: Date, now: Date): number {
  const startOfTarget = new Date(target.getFullYear(), target.getMonth(), target.getDate());
  const startOfNow = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((startOfTarget.getTime() - startOfNow.getTime()) / (1000 * 60 * 60 * 24));
}

function ddayInfo(closeDt: string | null): { label: string; urgent: boolean } | null {
  if (!closeDt) return null;
  const days = daysUntil(new Date(closeDt), new Date());
  if (days < 0) return null;
  return { label: days === 0 ? "D-Day" : `D-${days}`, urgent: days <= 3 };
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={600}>
        {value}
      </Typography>
    </Box>
  );
}

// 공개(비로그인) 공고 상세 — 리포트에서 공고를 클릭하면 온다. 내부 관리자 화면(NoticeDetailPage)
// 과 같은 상세 분석 내용(탭·첨부원문)을 그대로 보여준다(2026-09-12 사용자 지시 — "공고탐색의
// 공고 상세페이지와 내용이 모두 들어가게"). 담당자 배정·자사 제품 충족판정 등 내부 전용
// 항목만 빠진다(app/services/notice_strategy.py get_public_notice_summary가 걸러서 줌 — A2
// requirement 자체엔 그런 내부 판정 필드가 아예 없어 그대로 노출해도 안전함).
export function PublicNoticeDetailPage() {
  const { token, noticeId } = useParams<{ token: string; noticeId: string }>();
  const noticeIdNum = Number(noticeId);
  const queryClient = useQueryClient();
  const queryKey = ["public-notice", token, noticeId];
  const { data, isLoading, isError } = useQuery({
    queryKey,
    queryFn: () => fetchPublicNotice(token!, noticeIdNum),
    retry: false,
  });

  // 행동 데이터 수집(2026-09-23) — 상세페이지 도달 자체를 신호로 남긴다. 실패해도 화면
  // 동작에 영향 없어야 하므로(부가 신호일 뿐) catch 없이 무시한다. StrictMode 개발 모드
  // 이중 실행은 서버 쪽 de-dupe 윈도우(5분)가 흡수한다.
  useEffect(() => {
    if (token) void recordPublicNoticeView(token, noticeIdNum);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, noticeIdNum]);

  const likeMutation = useMutation({
    mutationFn: (liked: boolean) => setPublicNoticeLike(token!, noticeIdNum, liked),
    onSuccess: (result) => {
      queryClient.setQueryData<PublicNoticeDetail>(queryKey, (prev) => (prev ? { ...prev, liked: result.liked } : prev));
    },
  });
  const requirementsQuery = useQuery({
    queryKey: ["public-notice-requirements", token, noticeId],
    queryFn: () => fetchPublicRequirements(token!, noticeIdNum),
  });
  const extractionQuery = useQuery({
    queryKey: ["public-notice-extraction", token, noticeId],
    queryFn: () => fetchPublicExtraction(token!, noticeIdNum),
  });

  // "AI 사업 추진 전략" — 예전엔 별도 페이지(/strategy)로 이동했으나, 이 페이지 하단에 섹션으로
  // 붙인다(2026-09-12 사용자 지시 — "새로운 페이지로 가지 말고 현재 페이지 하단에"). 페이지를
  // 열자마자 자동으로 생성하지 않고(LLM 비용 발생) 버튼을 눌러야만 조회를 시작한다.
  const [strategyRequested, setStrategyRequested] = useState(false);
  const strategyQuery = useQuery({
    queryKey: ["public-notice-strategy", token, noticeId],
    queryFn: () => generatePublicNoticeStrategy(token!, noticeIdNum),
    enabled: strategyRequested,
    retry: false,
    refetchInterval: (query) => (query.state.data?.status === "pending" ? 3000 : false),
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
        <Typography>공고를 찾을 수 없습니다.</Typography>
      </Box>
    );
  }

  const dday = ddayInfo(data.close_dt);
  const summary = data.ai_summary as
    | { project_period?: string; project_budget?: string; purpose?: string; sub_business?: string }
    | null;
  const alreadyGenerated = data.strategy?.status === "done";

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default", py: { xs: 3, md: 6 } }}>
      <Stack spacing={3} sx={{ maxWidth: 1100, mx: "auto", px: 2 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Logo size={34} />
        </Stack>

        <Button component={RouterLink} to={`/r/${token}`} startIcon={<ArrowBackIcon />} sx={{ alignSelf: "flex-start" }}>
          리포트로 돌아가기
        </Button>

        <Card sx={{ p: { xs: 2, md: 3 } }}>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
            <Chip label={data.notice_type} size="small" color="secondary" variant="outlined" />
            <Chip label={data.notice_status_label} size="small" variant="outlined" />
            <Chip label={data.work_type_label} size="small" variant="outlined" />
            <Chip
              label={BID_STATUS_LABELS[data.bid_status]}
              size="small"
              color={data.bid_status === "in_progress" ? "error" : "default"}
              variant={data.bid_status === "in_progress" ? "filled" : "outlined"}
              sx={{ fontWeight: 700 }}
            />
          </Stack>

          <Typography variant="h2" sx={{ mb: 1 }}>
            {data.title}
          </Typography>

          {summary?.sub_business && <Field label="세부사업(내역사업)" value={summary.sub_business} />}

          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap sx={{ mt: 2 }}>
            <Field label="총사업기간" value={summary?.project_period || "미분석"} />
            <Field label="사업비" value={summary?.project_budget || formatPrice(data.est_price)} />
          </Stack>

          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap sx={{ mt: 2 }}>
            <Field label="발주기관" value={data.org_name ?? "미상"} />
            <Field label="지역" value={data.region ?? "—"} />
            <Field label="공고번호" value={data.notice_no ?? "미부여"} />
          </Stack>

          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap alignItems="center" sx={{ mt: 2 }}>
            <Field
              label="게시일"
              value={data.open_dt ? new Date(data.open_dt).toLocaleDateString("ko-KR") : "—"}
            />
            <Field
              label="마감일"
              value={data.close_dt ? new Date(data.close_dt).toLocaleString("ko-KR") : "—"}
            />
            {dday && (
              <Chip label={dday.label} size="medium" color={dday.urgent ? "error" : "warning"} variant="filled" sx={{ fontWeight: 700 }} />
            )}
          </Stack>

          {summary?.purpose && (
            <Box sx={{ mt: 2, p: 1.5, borderRadius: 1, bgcolor: "action.hover" }}>
              <Typography variant="body2" fontWeight={600} sx={{ whiteSpace: "pre-wrap" }}>
                과제목표 — {summary.purpose}
              </Typography>
            </Box>
          )}

          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 3 }}>
            <Button
              variant="outlined"
              startIcon={isAttachmentDownloadUrl(data.url) ? <DownloadOutlinedIcon /> : <OpenInNewIcon />}
              component="a"
              href={data.url}
              target="_blank"
              rel="noreferrer"
            >
              {isAttachmentDownloadUrl(data.url) ? "규격서 파일 다운로드" : "공고원문보기"}
            </Button>
            {/* 이미 생성된 전략이 있으면(2026-09-12) 버튼을 다시 안 보여준다 — 아래 섹션에
                바로 나온다. LLM을 다시 부르는 게 아니라 캐시된 결과 조회일 뿐이라 재클릭
                자체가 의미 없기 때문. */}
            {!alreadyGenerated && !strategyRequested && (
              <Button variant="contained" startIcon={<AutoAwesomeOutlinedIcon />} onClick={() => setStrategyRequested(true)}>
                AI 사업 추진 전략
              </Button>
            )}
            <Tooltip title={data.liked ? "좋아요 취소" : "좋아요"}>
              <span>
                <IconButton
                  color="error"
                  disabled={likeMutation.isPending}
                  onClick={() => likeMutation.mutate(!data.liked)}
                  aria-label={data.liked ? "좋아요 취소" : "좋아요"}
                >
                  {data.liked ? <FavoriteIcon /> : <FavoriteBorderOutlinedIcon />}
                </IconButton>
              </span>
            </Tooltip>
          </Stack>
        </Card>

        {(alreadyGenerated || strategyRequested) && (
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
            {(alreadyGenerated || strategyQuery.data?.status === "done") && (
              <Chip label="AI 생성 참고자료" size="small" color="primary" variant="outlined" sx={{ mb: 1 }} />
            )}
            <Divider sx={{ my: 2 }} />

            {!alreadyGenerated && (strategyQuery.isLoading || strategyQuery.data?.status === "pending") && (
              <Stack alignItems="center" spacing={2} sx={{ py: 8 }}>
                <CircularProgress size={36} />
                <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
                  처음 열람하는 공고라 AI가 분석 중입니다 — 최대 1분 정도 걸릴 수 있습니다.
                  <br />
                  이 섹션을 벗어나지 않아도 자동으로 갱신됩니다.
                </Typography>
              </Stack>
            )}

            {!alreadyGenerated && strategyQuery.isError && (
              <Stack spacing={2} sx={{ py: 3 }}>
                <Alert severity="error">
                  {(strategyQuery.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
                    "전략 생성에 실패했습니다."}
                </Alert>
                <Button variant="outlined" onClick={() => strategyQuery.refetch()} sx={{ alignSelf: "flex-start" }}>
                  다시 시도
                </Button>
              </Stack>
            )}

            {alreadyGenerated && <MarkdownContent>{data.strategy!.strategy_md}</MarkdownContent>}
            {!alreadyGenerated && strategyQuery.data?.status === "done" && strategyQuery.data.strategy_md && (
              <MarkdownContent>{strategyQuery.data.strategy_md}</MarkdownContent>
            )}

            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 3, textAlign: "center" }}>
              이 내용은 검토를 돕는 참고자료이며, 참여 여부에 대한 최종 판단은 별도로 필요합니다.
            </Typography>
          </Card>
        )}

        <AnalysisTabsSection requirements={requirementsQuery.data} extraction={extractionQuery.data} />
        <AnalyzedDocumentsSection extraction={extractionQuery.data} />
      </Stack>
    </Box>
  );
}
