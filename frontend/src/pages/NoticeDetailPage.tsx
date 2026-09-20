import ArrowBackIcon from "@mui/icons-material/ArrowBackIosNewOutlined";
import ArrowForwardIcon from "@mui/icons-material/ArrowForwardIosOutlined";
import { Button, Card, Chip, CircularProgress, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { fetchLatestExtraction, fetchRequirements, runExtraction, runStructuring, type LlmModel } from "@/api/analysis";
import { fetchFilterOptions, fetchNeighbors, fetchNoticeDetail } from "@/api/notices";
import { AnalysisTabsSection } from "@/components/notice-detail/AnalysisTabsSection";
import { AnalyzedDocumentsSection } from "@/components/notice-detail/AnalyzedDocumentsSection";
import { NoticeTopSection } from "@/components/notice-detail/NoticeTopSection";
import { useToast } from "@/components/ToastProvider";

export function NoticeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const noticeId = Number(id);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const detailQuery = useQuery({
    queryKey: ["notice", noticeId],
    queryFn: () => fetchNoticeDetail(noticeId),
  });

  // 관심주제 추가(TopicEditor)에서 고를 수 있는 전체 목록 — 목록 페이지 필터바와 같은 조회.
  const filterOptionsQuery = useQuery({ queryKey: ["filter-options"], queryFn: fetchFilterOptions });

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
    // onError가 없어서(2026-09-12 발견) run_extraction_pilot 자체가 실제 HTTP 에러(네트워크
    // 장애 등, status:"failed" 정상 응답과는 다름 — 그건 아래 runAiAnalysis에서 따로 처리)를
    // 던지면 "버튼을 눌러도 반응이 없다"로만 보였다. structureMutation과 같은 패턴으로 표시.
    onError: (error) => {
      setAnalysisError(
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "첨부문서 추출에 실패했습니다."
      );
    },
  });

  const requirementsQuery = useQuery({
    queryKey: ["notice-requirements", noticeId],
    queryFn: () => fetchRequirements(noticeId),
  });

  // 실패 사유를 화면에 보여주기 위한 상태(2026-09-06) — 예전엔 추출 실패(run_extraction_pilot이
  // 정상 200 응답으로 status:"failed"를 돌려주는 경우, 즉 apis.data.go.kr 타임아웃 등 외부
  // API 장애)를 아무 표시 없이 조용히 멈춰서, 사용자가 "버튼을 눌러도 반응이 없다"고 느꼈다
  // (실제로 이 문제로 문의받음). 구조화(A2) 실패는 HTTPException이라 mutation.error로 잡힌다.
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const structureMutation = useMutation({
    mutationFn: (m: LlmModel) => runStructuring(noticeId, m),
    onSuccess: () => {
      setAnalysisError(null);
      queryClient.invalidateQueries({ queryKey: ["notice-requirements", noticeId] });
      notify("success", "AI분석이 완료됐습니다.");
    },
    onError: (error) => {
      setAnalysisError(
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "AI분석(구조화)에 실패했습니다."
      );
    },
  });

  // "AI분석 실행" 하나로 A1(첨부문서 추출)+A2(구조화)를 순서대로 실행한다(2026-09-05 요청 —
  // 첨부문서 추출 화면을 따로 안 보여주므로, 안 돼 있으면 여기서 먼저 조용히 실행). 모델 선택은
  // NoticeTopSection의 확인 팝업에서 받는다(비용 발생 고지 후 확인) — 이미 분석된 공고도
  // "재분석" 버튼으로 다시 실행 가능(analysis.ver가 새로 쌓임).
  //
  // 기존 추출 결과는 "문서를 하나라도 찾았을 때만" 재사용한다(2026-09-06 수정) — 예전엔
  // A1 상태가 "done"이기만 하면 무조건 재사용해서, A1이 버그로 0건을 찾은 채 끝난 공고는
  // "재분석"을 눌러도 그 텅 빈 결과를 그대로 재사용하고 A1을 다시 안 돌렸다(나라장터 g2b
  // 첨부 발견 로직 버그 수정 건과 맞물려 실제로 발견됨). 0건이면 매번 새로 추출을 시도해야
  // 버그 수정·일시적 API 실패 이후 재시도가 실제로 효과가 있다.
  async function runAiAnalysis(model: LlmModel) {
    setAnalysisError(null);
    const canReuse = extractionQuery.data?.status === "done" && !alreadyAnalyzed && (extractionQuery.data.docs?.length ?? 0) > 0;
    let extraction;
    try {
      extraction = canReuse ? extractionQuery.data! : await extractMutation.mutateAsync();
    } catch {
      // 실제 HTTP 에러는 위 extractMutation.onError가 이미 analysisError에 표시했다 — 여기선
      // unhandled rejection으로 새지 않게 멈추기만 하면 된다.
      return;
    }
    if (extraction.status !== "done") {
      // run_extraction_pilot은 실패해도 예외를 던지지 않고 정상 응답(status:"failed")으로
      // 돌아온다 — extractMutation.error로는 안 잡히므로 여기서 직접 확인해야 한다.
      setAnalysisError(extraction.error || "첨부문서 추출에 실패했습니다.");
      return;
    }
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
        onRunAnalysis={runAiAnalysis}
        analysisPending={extractMutation.isPending || structureMutation.isPending}
        analysisDone={alreadyAnalyzed}
        analysisError={analysisError}
        allTopics={filterOptionsQuery.data?.topics ?? []}
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

      <AnalysisTabsSection requirements={requirementsQuery.data} extraction={extractionQuery.data} noticeId={noticeId} />

      {/* 분석대상 첨부파일 원문 — 페이지 최하단 별도 섹션(2026-09-08 요청). */}
      <AnalyzedDocumentsSection extraction={extractionQuery.data} />
    </Stack>
  );
}
