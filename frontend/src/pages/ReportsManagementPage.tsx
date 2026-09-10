import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import {
  Alert,
  Box,
  Button,
  Card,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";

import type { LlmModel } from "@/api/analysis";
import { fetchCustomers } from "@/api/customerInterests";
import { fetchCustomersFull, generateReportCommentary } from "@/api/customers";
import { fetchReports, generateReport } from "@/api/reports";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

const SELECTABLE_MODELS: { value: LlmModel; label: string }[] = [
  { value: "haiku", label: "Haiku (저렴)" },
  { value: "sonnet", label: "Sonnet (기본, 고품질)" },
];

// 보고서 관리(2026-09-05 메뉴 재정리 — 기존 "고객 관심 주제" 화면에서 리포트 부분만 분리) —
// 고객마다 여러 건씩 쌓이는 리포트를 다루는 화면이라 고객 상세(1건짜리 설정)와는 별도가 맞다고
// 판단. 매칭 조건 설정은 "고객 관리 > 상세" 화면에서.
export function ReportsManagementPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const customersQuery = useQuery({ queryKey: ["customers"], queryFn: fetchCustomers });
  const customersFullQuery = useQuery({ queryKey: ["customers-full"], queryFn: fetchCustomersFull });

  const [customerId, setCustomerId] = useState<number | null>(null);
  useEffect(() => {
    if (customerId === null && customersQuery.data && customersQuery.data.length > 0) {
      setCustomerId(customersQuery.data[0].id);
    }
  }, [customerId, customersQuery.data]);

  const reportsQuery = useQuery({
    queryKey: ["reports", customerId],
    queryFn: () => fetchReports(customerId!),
    enabled: customerId !== null,
  });

  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  // onError가 없어서 리포트 생성이 실패해도(예: 나라장터 API 지연으로 인한 타임아웃) 아무
  // 표시가 없던 문제(2026-09-07 발견·73번 항목) — 성공·실패 모두 토스트로 알린다.
  const generateReportMutation = useMutation({
    mutationFn: () => generateReport(customerId!),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: ["reports", customerId] });
      void navigator.clipboard?.writeText(`${window.location.origin}/r/${report.token}`);
      setCopiedToken(report.token);
      notify("success", "리포트를 생성했습니다 — 링크가 클립보드에 복사됐습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "리포트 생성에 실패했습니다.")),
  });

  const currentCustomer = (customersFullQuery.data ?? []).find((c) => c.id === customerId);
  const hasProfileSummary = Boolean(currentCustomer?.profile_summarized_at);

  const [commentaryTargetReportId, setCommentaryTargetReportId] = useState<number | null>(null);
  const [commentaryModel, setCommentaryModel] = useState<LlmModel>("sonnet");
  const commentaryMutation = useMutation({
    mutationFn: (reportId: number) => generateReportCommentary(customerId!, reportId, commentaryModel),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports", customerId] });
      notify("success", "AI 코멘트를 생성했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "AI 코멘트 생성에 실패했습니다.")),
  });

  function confirmCommentary() {
    if (commentaryTargetReportId === null) return;
    const reportId = commentaryTargetReportId;
    setCommentaryTargetReportId(null);
    commentaryMutation.mutate(reportId);
  }

  return (
    <Stack spacing={3} sx={{ maxWidth: 720 }}>
      <Box>
        <Typography variant="h2">보고서 관리</Typography>
        <Typography variant="body2" color="text.secondary">
          고객별 관심분야 리포트를 생성·발송 전 확인합니다. 매칭 조건은 "고객 관리" 상세
          화면에서 설정합니다.
        </Typography>
      </Box>

      <TextField
        select
        label="고객"
        sx={{ maxWidth: 320 }}
        value={customerId ?? ""}
        onChange={(e) => setCustomerId(Number(e.target.value))}
      >
        {(customersQuery.data ?? []).map((c) => (
          <MenuItem key={c.id} value={c.id}>
            {c.name} {c.plan_tier === "internal" ? "(그립 자신)" : `(${c.plan_tier})`}
          </MenuItem>
        ))}
      </TextField>

      <Card sx={{ p: 3 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="h3">리포트 목록</Typography>
          <Button
            size="small"
            variant="outlined"
            disabled={generateReportMutation.isPending || customerId === null}
            onClick={() => generateReportMutation.mutate()}
          >
            지금 생성
          </Button>
        </Stack>
        {copiedToken && (
          <Typography variant="caption" color="success.main" sx={{ display: "block", mb: 1 }}>
            링크가 클립보드에 복사됐습니다: /r/{copiedToken}
          </Typography>
        )}
        <List dense disablePadding>
          {(reportsQuery.data ?? []).map((r) => (
            <ListItem
              key={r.id}
              disableGutters
              secondaryAction={
                <Tooltip title={hasProfileSummary ? "" : "고객 프로필 요약을 먼저 생성하세요(고객 관리 상세 화면)"}>
                  <span>
                    <Button
                      size="small"
                      startIcon={<AutoAwesomeOutlinedIcon fontSize="small" />}
                      disabled={!hasProfileSummary || commentaryMutation.isPending}
                      onClick={() => setCommentaryTargetReportId(r.id)}
                    >
                      {r.ai_generated_at ? "AI 코멘트 재생성" : "AI 코멘트 생성"}
                    </Button>
                  </span>
                </Tooltip>
              }
            >
              <ListItemText
                primary={`${new Date(r.generated_at).toLocaleDateString("ko-KR")} · ${r.summary.total}건`}
                secondary={
                  <RouterLink to={`/r/${r.token}`} target="_blank" rel="noreferrer">
                    /r/{r.token} (조회 {r.view_count}회)
                  </RouterLink>
                }
              />
            </ListItem>
          ))}
          {(reportsQuery.data ?? []).length === 0 && (
            <Typography variant="body2" color="text.secondary">
              아직 생성한 리포트가 없습니다.
            </Typography>
          )}
        </List>
      </Card>

      <Dialog open={commentaryTargetReportId !== null} onClose={() => setCommentaryTargetReportId(null)} maxWidth="xs" fullWidth>
        <DialogTitle>AI 코멘트 생성</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            LLM 호출 비용이 발생합니다. 공고 선별 결과는 그대로 두고, 각 공고가 왜 이 고객에게
            의미있는지 코멘트만 덧붙입니다 — 이미 생성된 코멘트가 있으면 덮어씁니다.
          </Alert>
          <RadioGroup value={commentaryModel} onChange={(e) => setCommentaryModel(e.target.value as LlmModel)}>
            {SELECTABLE_MODELS.map((m) => (
              <FormControlLabel key={m.value} value={m.value} control={<Radio />} label={m.label} />
            ))}
          </RadioGroup>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCommentaryTargetReportId(null)}>취소</Button>
          <Button variant="contained" onClick={confirmCommentary}>
            확인
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
