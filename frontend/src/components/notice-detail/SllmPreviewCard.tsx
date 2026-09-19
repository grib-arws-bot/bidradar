import { Alert, Card, Chip, Stack, Table, TableBody, TableCell, TableRow, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchSllmRequirementPreview, startSllmRequirementPreview, type Requirement } from "@/api/analysis";
import { LoadingButton } from "@/components/LoadingButton";
import { useToast } from "@/components/ToastProvider";

const OP_LABEL: Record<string, string> = { gte: "이상", lte: "이하", eq: "일치", contains: "포함", manual: "서술형" };

function requirementValueLabel(req: Requirement): string {
  return req.req_value ? `${req.req_value}${req.req_unit ?? ""} ${OP_LABEL[req.op]}` : OP_LABEL[req.op];
}

// 사내 sLLM(A, extract-requirements) 요구사항 추출 무료 미리보기(2026-09-20) — 비용이 드는
// "AI분석(Haiku, A2)"을 실제로 돌릴 가치가 있는지 미리 가늠하기 위한 보조 카드. 판정 근거로
// 쓰지 않는다("확인 필요" 딱지를 항상 붙인다) — NoticeTopSection의 AI분석과는 물리적으로
// 별개 결과(analysis_sllm_preview)이며 공개 리포트 화면에는 노출하지 않는다(관리자 전용).
export function SllmPreviewCard({ noticeId, enabled }: { noticeId: number; enabled: boolean }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const queryKey = ["notice-sllm-preview", noticeId];

  const previewQuery = useQuery({
    queryKey,
    queryFn: () => fetchSllmRequirementPreview(noticeId),
    enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 3000 : false;
    },
  });

  const startMutation = useMutation({
    mutationFn: () => startSllmRequirementPreview(noticeId),
    onSuccess: (data) => queryClient.setQueryData(queryKey, data),
    onError: (error) => {
      notify(
        "error",
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "sLLM 미리보기 시작에 실패했습니다."
      );
    },
  });

  if (!enabled) return null;

  const preview = previewQuery.data;
  const inProgress = preview?.status === "queued" || preview?.status === "running";

  return (
    <Card sx={{ p: 3 }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
        <Typography variant="h3">sLLM 미리보기</Typography>
        <Chip label="무료 · 확인 필요" size="small" variant="outlined" />
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        AI분석(Haiku)을 실제로 돌리기 전에, 사내 sLLM으로 요구사항을 무료로 먼저 훑어봅니다.
        정식 분석이 아니므로 참고용으로만 쓰세요.
      </Typography>

      {!preview && (
        <LoadingButton
          variant="outlined"
          size="small"
          loading={startMutation.isPending}
          onClick={() => startMutation.mutate()}
        >
          미리보기 시작
        </LoadingButton>
      )}

      {inProgress && (
        <LoadingButton variant="outlined" size="small" loading loadingText="처리 중..." disabled>
          처리 중
        </LoadingButton>
      )}
      {inProgress && preview?.chunks_total != null && (
        <Typography variant="caption" color="text.secondary" sx={{ ml: 1.5 }}>
          {preview.chunks_processed ?? 0}/{preview.chunks_total} 청크
        </Typography>
      )}

      {preview?.status === "failed" && (
        <Stack spacing={1.5} alignItems="flex-start">
          <Alert severity="error">sLLM 미리보기 실패: {preview.error}</Alert>
          <LoadingButton variant="outlined" size="small" loading={startMutation.isPending} onClick={() => startMutation.mutate()}>
            다시 시도
          </LoadingButton>
        </Stack>
      )}

      {preview?.status === "done" && (
        <Stack spacing={1.5}>
          <LoadingButton
            variant="text"
            size="small"
            loading={startMutation.isPending}
            onClick={() => startMutation.mutate()}
            sx={{ alignSelf: "flex-start" }}
          >
            다시 미리보기
          </LoadingButton>
          {(preview.requirements?.length ?? 0) === 0 ? (
            <Typography variant="body2" color="text.secondary">
              sLLM이 근거를 확인할 수 있는 요구사항을 찾지 못했습니다.
            </Typography>
          ) : (
            <Table size="small">
              <TableBody>
                {preview.requirements!.map((req, i) => (
                  <TableRow key={i}>
                    <TableCell sx={{ whiteSpace: "nowrap", border: 0, pl: 0 }}>{req.category}</TableCell>
                    <TableCell sx={{ border: 0 }}>{req.req_text}</TableCell>
                    <TableCell className="tnum" sx={{ whiteSpace: "nowrap", border: 0 }}>
                      {requirementValueLabel(req)}
                    </TableCell>
                    <TableCell sx={{ border: 0 }}>
                      <Typography variant="caption" color="text.secondary">
                        {req.cite}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {(preview.rejected_ungrounded_count ?? 0) > 0 && (
            <Typography variant="caption" color="text.secondary">
              근거를 원문에서 확인할 수 없어 {preview.rejected_ungrounded_count}건 제외됨
              {(preview.duplicate_count ?? 0) > 0 && `, 중복 ${preview.duplicate_count}건 제거됨`}
            </Typography>
          )}
        </Stack>
      )}
    </Card>
  );
}
