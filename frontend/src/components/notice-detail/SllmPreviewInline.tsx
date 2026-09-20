import { Alert, Stack, Table, TableBody, TableCell, TableRow, Typography } from "@mui/material";

import { type SllmRequirementPreview } from "@/api/analysis";
import { LoadingButton } from "@/components/LoadingButton";

import { requirementValueLabel } from "./requirementFormat";

// A2(Haiku)가 아직 안 끝난 공고 상세분석 자리에 대신 보여주는 무료 sLLM 미리보기(2026-09-20,
// 의사결정_로그 184번) — "확인 필요" 딱지가 항상 붙는 미검증 결과다. AI분석(A2)이 완료되면
// 이 자리를 그 결과가 대체한다(AnalysisTabsSection의 {summary && (...)} 분기로 자연히 넘어감)
// — 정식 분석이 미리보기를 덮어쓰는 것이지, 둘을 나란히 보여주지 않는다.
export function SllmPreviewInline({
  preview,
  onRetry,
  retrying,
}: {
  preview: SllmRequirementPreview | null | undefined;
  onRetry: () => void;
  retrying: boolean;
}) {
  const inProgress = preview?.status === "queued" || preview?.status === "running";

  return (
    <Stack spacing={1.5} sx={{ py: 2 }}>
      <Stack direction="row" alignItems="center" spacing={1}>
        <Typography variant="body2" color="text.secondary">
          정식 AI분석(Haiku) 전 사내 sLLM으로 먼저 훑어본 무료 미리보기입니다 — 참고용으로만 쓰세요.
        </Typography>
      </Stack>

      {!preview && (
        <Typography variant="body2" color="text.secondary">
          미리보기를 준비하고 있습니다...
        </Typography>
      )}

      {inProgress && (
        <Stack direction="row" alignItems="center" spacing={1}>
          <LoadingButton variant="outlined" size="small" loading loadingText="처리 중..." disabled>
            처리 중
          </LoadingButton>
          {preview?.chunks_total != null && (
            <Typography variant="caption" color="text.secondary">
              {preview.chunks_processed ?? 0}/{preview.chunks_total} 청크
            </Typography>
          )}
        </Stack>
      )}

      {preview?.status === "failed" && (
        <Stack spacing={1.5} alignItems="flex-start">
          <Alert severity="error">sLLM 미리보기 실패: {preview.error}</Alert>
          <LoadingButton variant="outlined" size="small" loading={retrying} onClick={onRetry}>
            다시 시도
          </LoadingButton>
        </Stack>
      )}

      {preview?.status === "done" && (
        <Stack spacing={1.5}>
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
    </Stack>
  );
}
