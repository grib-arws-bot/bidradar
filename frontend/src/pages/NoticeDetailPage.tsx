import ArrowBackIcon from "@mui/icons-material/ArrowBackIosNewOutlined";
import ArrowForwardIcon from "@mui/icons-material/ArrowForwardIosOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMoreOutlined";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  Chip,
  CircularProgress,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { fetchLatestExtraction, fetchRequirements, runExtraction, runStructuring, type LlmModel } from "@/api/analysis";
import { followOrg } from "@/api/classification";
import { fetchNeighbors, fetchNoticeDetail } from "@/api/notices";
import { AnalysisTabsSection } from "@/components/notice-detail/AnalysisTabsSection";
import { NoticeTopSection } from "@/components/notice-detail/NoticeTopSection";

const DOC_KIND_LABEL: Record<string, string> = { pdf: "PDF", hwpx: "HWPX", hwp: "HWP", pptx: "PPTX", xlsx: "XLSX", zip: "ZIP", other: "기타" };
const EXTRACT_STATUS_LABEL: Record<string, string> = { running: "진행 중", done: "완료", failed: "실패" };

export function NoticeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const noticeId = Number(id);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

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

  const followMutation = useMutation({
    mutationFn: () => followOrg(noticeId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notice", noticeId] }),
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
    mutationFn: (model: LlmModel) => runStructuring(noticeId, model),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notice-requirements", noticeId] }),
  });

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
        onFollow={() => followMutation.mutate()}
        followPending={followMutation.isPending}
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

      <ExtractionCard noticeUrl={notice.url} extractionQuery={extractionQuery} extractMutation={extractMutation} />

      <AnalysisTabsSection
        notice={notice}
        extractionStatus={extractionQuery.data?.status}
        requirementsQuery={requirementsQuery}
        structureMutation={structureMutation}
      />
    </Stack>
  );
}

function ExtractionCard({
  noticeUrl,
  extractionQuery,
  extractMutation,
}: {
  noticeUrl: string;
  extractionQuery: ReturnType<typeof useQuery<Awaited<ReturnType<typeof fetchLatestExtraction>>>>;
  extractMutation: ReturnType<typeof useMutation<Awaited<ReturnType<typeof runExtraction>>, unknown, void>>;
}) {
  const isSupported = noticeUrl.includes("iris.go.kr") || noticeUrl.includes("g2b.go.kr");
  const result = extractMutation.data ?? extractionQuery.data;

  const errorDetail = (extractMutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;

  return (
    <Card sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
        <Box>
          <Typography variant="h3">심층 분석 (파일럿)</Typography>
          <Typography variant="caption" color="text.secondary">
            첨부문서를 다운로드해 텍스트만 추출합니다 — 충족 여부 판정은 아직 하지 않습니다. 지금은 IRIS·나라장터 입찰공고만 지원.
          </Typography>
        </Box>
        <Tooltip title={isSupported ? "" : "이 파일럿은 아직 IRIS·나라장터 입찰공고 공고만 지원합니다"}>
          <span>
            <Button
              variant="contained"
              size="small"
              startIcon={<AutoAwesomeOutlinedIcon />}
              disabled={!isSupported || extractMutation.isPending || result?.status === "running"}
              onClick={() => extractMutation.mutate()}
            >
              {extractMutation.isPending ? "추출 중..." : result ? "다시 추출" : "첨부문서 추출 실행"}
            </Button>
          </span>
        </Tooltip>
      </Stack>

      {errorDetail && (
        <Alert severity="error" sx={{ mb: 1.5 }}>
          {errorDetail}
        </Alert>
      )}

      {result && (
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              label={EXTRACT_STATUS_LABEL[result.status] ?? result.status}
              size="small"
              color={result.status === "done" ? "success" : result.status === "failed" ? "error" : "default"}
            />
            <Typography variant="body2" color="text.secondary">
              {result.docs.length > 0 ? `첨부 ${result.docs.length}건` : "첨부문서 없음"}
            </Typography>
          </Stack>

          {result.docs.map((doc, i) => (
            <Accordion key={`${doc.name}-${i}`} disableGutters variant="outlined">
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0, width: "100%" }}>
                  {doc.extract_ok ? (
                    <CheckCircleOutlineIcon fontSize="small" color="success" />
                  ) : (
                    <ErrorOutlineIcon fontSize="small" color="error" />
                  )}
                  <Chip label={DOC_KIND_LABEL[doc.kind] ?? doc.kind} size="small" />
                  <Typography variant="body2" noWrap sx={{ flex: 1 }}>
                    {doc.name}
                  </Typography>
                  {doc.extract_method && (
                    <Typography variant="caption" color="text.secondary">
                      {doc.extract_method}
                    </Typography>
                  )}
                </Stack>
              </AccordionSummary>
              <AccordionDetails>
                {doc.error && (
                  <Alert severity={doc.extract_ok ? "warning" : "error"} sx={{ mb: 1 }}>
                    {doc.error}
                  </Alert>
                )}
                {doc.text && (
                  <Box
                    sx={{
                      whiteSpace: "pre-wrap",
                      maxHeight: 400,
                      overflow: "auto",
                      p: 1.5,
                      bgcolor: "background.default",
                      borderRadius: 1,
                      fontSize: "0.8125rem",
                    }}
                  >
                    {doc.text}
                  </Box>
                )}
              </AccordionDetails>
            </Accordion>
          ))}
        </Stack>
      )}
    </Card>
  );
}
