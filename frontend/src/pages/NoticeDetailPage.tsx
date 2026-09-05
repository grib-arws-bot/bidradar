import ArrowBackIcon from "@mui/icons-material/ArrowBackIosNewOutlined";
import ArrowForwardIcon from "@mui/icons-material/ArrowForwardIosOutlined";
import { Button, Card, Chip, CircularProgress, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { fetchLatestExtraction, fetchRequirements, runExtraction, runStructuring, type LlmModel } from "@/api/analysis";
import { fetchNeighbors, fetchNoticeDetail } from "@/api/notices";
import { AnalysisTabsSection } from "@/components/notice-detail/AnalysisTabsSection";
import { NoticeTopSection } from "@/components/notice-detail/NoticeTopSection";

export function NoticeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const noticeId = Number(id);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [model, setModel] = useState<LlmModel>("haiku");

  const detailQuery = useQuery({
    queryKey: ["notice", noticeId],
    queryFn: () => fetchNoticeDetail(noticeId),
  });

  // 이전/다음이 목록의 필터·정렬 순서를 이어서 이동(S1-d) — 카드에서 넘어올 때 붙여온
  // 쿼리스트링을 그대로 재사용해서 neighbors를 조회한다.
  const neighborsQuery = useQuery({
    queryKey: ["notice-neighbors", noticeId, searchParams.toString()],
    queryFn: () => fetchNeighbors(noticeId, searchParams),
  });

  const extractionQuery = useQuery({
    queryKey: ["notice-extraction", noticeId],
    queryFn: () => fetchLatestExtraction(noticeId),
  });

  const extractMutation = useMutation({
    mutationFn: () => runExtraction(noticeId),
    onSuccess: (result) => queryClient.setQueryData(["notice-extraction", noticeId], result),
  });

  const requirementsQuery = useQuery({
    queryKey: ["notice-requirements", noticeId],
    queryFn: () => fetchRequirements(noticeId),
  });

  const structureMutation = useMutation({
    mutationFn: (m: LlmModel) => runStructuring(noticeId, m),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notice-requirements", noticeId] }),
  });

  // "AI분석 실행" 하나로 A1(첨부문서 추출)+A2(구조화)를 순서대로 실행한다(2026-09-05 요청 —
  // 첨부문서 추출 화면을 따로 안 보여주므로, 안 돼 있으면 여기서 먼저 조용히 실행).
  async function runAiAnalysis() {
    const extraction = extractionQuery.data?.status === "done" ? extractionQuery.data : await extractMutation.mutateAsync();
    if (extraction.status !== "done") return; // 추출 실패 — extractMutation.error가 AI분석 버튼 쪽엔 안 보이지만 재시도 가능
    structureMutation.mutate(model);
  }

  if (detailQuery.isLoading) {
    return (
      <Stack alignItems="center" sx={{ py: 8 }}>
        <CircularProgress />
      </Stack>
    );
  }

  if (!detailQuery.data) {
    return <Typography>공고를 찾을 수 없습니다.</Typography>;
  }

  const notice = detailQuery.data;
  const qs = searchParams.toString();
  const alreadyAnalyzed = requirementsQuery.data?.step === "A2_structure";

  return (
    // 우측 끝까지 여백을 다 쓴다(2026-09-05 요청) — 목록 페이지처럼 maxWidth로 좁히지 않음.
    <Stack spacing={3} sx={{ width: "100%" }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Button component={RouterLink} to={`/notices?${qs}`} size="small">
          ← 목록으로
        </Button>
        <Stack direction="row" spacing={1} alignItems="center">
          <Tooltip title="이전 (현재 필터·정렬 기준)">
            <span>
              <IconButton
                size="small"
                disabled={!neighborsQuery.data?.prev_id}
                onClick={() => navigate(`/notices/${neighborsQuery.data?.prev_id}?${qs}`)}
              >
                <ArrowBackIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="다음 (현재 필터·정렬 기준)">
            <span>
              <IconButton
                size="small"
                disabled={!neighborsQuery.data?.next_id}
                onClick={() => navigate(`/notices/${neighborsQuery.data?.next_id}?${qs}`)}
              >
                <ArrowForwardIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </Stack>

      <NoticeTopSection
        notice={notice}
        summary={requirementsQuery.data?.summary}
        model={model}
        onModelChange={setModel}
        onRunAnalysis={runAiAnalysis}
        analysisPending={extractMutation.isPending || structureMutation.isPending}
        analysisDone={alreadyAnalyzed}
      />

      {/* 시드 데이터의 참여자격 요건(requirement 테이블) — S8 이전부터 있던 별개 개념, 실제
          수집기가 채우지 않아 대부분 공고는 비어 있다. */}
      {notice.requirements.length > 0 && (
        <Card sx={{ p: 3 }}>
          <Typography variant="h3" sx={{ mb: 1.5 }}>
            참여 자격 요건
          </Typography>
          <Stack spacing={1}>
            {notice.requirements.map((req) => (
              <Stack
                key={req.id}
                direction="row"
                spacing={1.5}
                sx={{ p: 1, borderRadius: 1, bgcolor: req.we_qualify === false ? "error.lighter" : "transparent" }}
              >
                <Chip label={req.type} size="small" />
                <Typography
                  variant="body2"
                  sx={{ color: req.we_qualify === false ? "error.main" : "text.primary", fontWeight: req.we_qualify === false ? 600 : 400 }}
                >
                  {req.value}
                  {req.we_qualify === false && " — 미충족"}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </Card>
      )}

      <AnalysisTabsSection requirementsQuery={requirementsQuery} />
    </Stack>
  );
}
