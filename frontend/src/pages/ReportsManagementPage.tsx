import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
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
  ListItemButton,
  ListItemText,
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
import { deleteReport, fetchReports, generateReport, sendReport } from "@/api/reports";
import { fetchSettings, updateSettings } from "@/api/settings";
import { LoadingButton, LoadingIconButton } from "@/components/LoadingButton";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

const SELECTABLE_MODELS: { value: LlmModel; label: string }[] = [
  { value: "haiku", label: "Haiku (저렴)" },
  { value: "sonnet", label: "Sonnet (기본, 고품질)" },
];

// 보고서 관리(2026-09-05 메뉴 재정리, 2026-09-12 목록형으로 재구성 — 고객이 늘어나면
// 드롭다운보다 왼쪽 목록에서 바로 훑어보는 편이 낫다는 사용자 지시) — 왼쪽 고객 목록, 오른쪽
// 선택된 고객의 보고서 목록(생성·발송·삭제). 매칭 조건 설정은 "고객 관리 > 상세" 화면에서.
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

  const deleteReportMutation = useMutation({
    mutationFn: (reportId: number) => deleteReport(customerId!, reportId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports", customerId] });
      notify("success", "보고서를 삭제했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "보고서 삭제에 실패했습니다.")),
  });

  const sendReportMutation = useMutation({
    mutationFn: (reportId: number) => sendReport(customerId!, reportId),
    onSuccess: ({ sent_to }) => notify("success", `발송했습니다: ${sent_to.join(", ")}`),
    onError: (error) => notify("error", apiErrorMessage(error, "보고서 발송에 실패했습니다.")),
  });

  const currentCustomer = (customersFullQuery.data ?? []).find((c) => c.id === customerId);
  const hasProfileSummary = Boolean(currentCustomer?.profile_summarized_at);
  const hasRecipients = (currentCustomer?.report_recipient_emails.length ?? 0) > 0;

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

  // 보고서 자동 삭제 보관기간 설정(2026-09-12 사용자 지시) — 생성 후 N일 지나면 다음 리포트
  // 생성 시점에 자동으로 지워진다(app/services/interest_report.py delete_expired_reports).
  const settingsQuery = useQuery({ queryKey: ["app-settings"], queryFn: fetchSettings });
  const [retentionInput, setRetentionInput] = useState("");
  useEffect(() => {
    if (settingsQuery.data) setRetentionInput(settingsQuery.data.report_retention_days?.toString() ?? "");
  }, [settingsQuery.data]);
  const saveSettingsMutation = useMutation({
    mutationFn: (days: number | null) => updateSettings({ report_retention_days: days }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["app-settings"] });
      notify("success", "설정을 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "설정 저장에 실패했습니다.")),
  });

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h2">보고서 관리</Typography>
        <Typography variant="body2" color="text.secondary">
          고객별 관심분야 리포트를 생성·발송·삭제합니다. 매칭 조건은 "고객 관리" 상세 화면에서
          설정합니다.
        </Typography>
      </Box>

      <Card sx={{ p: 3 }}>
        <Typography variant="h3" sx={{ mb: 1.5 }}>
          설정
        </Typography>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <TextField
            size="small"
            type="number"
            label="보고서 자동 삭제 보관기간(일)"
            value={retentionInput}
            onChange={(e) => setRetentionInput(e.target.value)}
            slotProps={{ htmlInput: { min: 1 } }}
            sx={{ width: 260 }}
            helperText="생성 후 이 기간이 지나면 자동 삭제됩니다. 비워두면 자동 삭제하지 않습니다."
          />
          <LoadingButton
            variant="outlined"
            loading={saveSettingsMutation.isPending}
            loadingText="저장 중..."
            onClick={() => saveSettingsMutation.mutate(retentionInput.trim() === "" ? null : Number(retentionInput))}
          >
            저장
          </LoadingButton>
        </Stack>
      </Card>

      <Stack direction="row" spacing={3} alignItems="flex-start">
        <Card sx={{ width: 280, flexShrink: 0 }}>
          <Typography variant="h3" sx={{ p: 2, pb: 1 }}>
            고객
          </Typography>
          <List dense disablePadding>
            {(customersQuery.data ?? []).map((c) => (
              <ListItem key={c.id} disablePadding>
                <ListItemButton selected={c.id === customerId} onClick={() => setCustomerId(c.id)}>
                  <ListItemText
                    primary={c.name}
                    secondary={c.plan_tier === "internal" ? "그립 자신" : c.plan_tier}
                  />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
        </Card>

        <Card sx={{ p: 3, flexGrow: 1 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="h3">리포트 목록</Typography>
            <LoadingButton
              variant="outlined"
              loading={generateReportMutation.isPending}
              loadingText="생성 중..."
              disabled={customerId === null}
              onClick={() => generateReportMutation.mutate()}
            >
              보고서 생성
            </LoadingButton>
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
                  <Stack direction="row" spacing={0.5}>
                    <Tooltip title={hasProfileSummary ? "" : "고객 프로필 요약을 먼저 생성하세요(고객 관리 상세 화면)"}>
                      <span>
                        <LoadingButton
                          size="small"
                          startIcon={<AutoAwesomeOutlinedIcon fontSize="small" />}
                          loading={commentaryMutation.isPending && commentaryMutation.variables === r.id}
                          disabled={!hasProfileSummary || commentaryMutation.isPending}
                          onClick={() => setCommentaryTargetReportId(r.id)}
                        >
                          {r.ai_generated_at ? "AI 코멘트 재생성" : "AI 코멘트 생성"}
                        </LoadingButton>
                      </span>
                    </Tooltip>
                    <Tooltip title={hasRecipients ? "설정된 수신자에게 발송" : "고객 상세 화면에서 보고서 수신자 이메일을 먼저 등록하세요"}>
                      <span>
                        <LoadingIconButton
                          size="small"
                          loading={sendReportMutation.isPending && sendReportMutation.variables === r.id}
                          disabled={!hasRecipients || sendReportMutation.isPending}
                          onClick={() => sendReportMutation.mutate(r.id)}
                        >
                          <SendOutlinedIcon fontSize="small" />
                        </LoadingIconButton>
                      </span>
                    </Tooltip>
                    <Tooltip title="삭제">
                      <LoadingIconButton
                        size="small"
                        loading={deleteReportMutation.isPending && deleteReportMutation.variables === r.id}
                        disabled={deleteReportMutation.isPending}
                        onClick={() => deleteReportMutation.mutate(r.id)}
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </LoadingIconButton>
                    </Tooltip>
                  </Stack>
                }
              >
                <ListItemText
                  primary={`${new Date(r.generated_at).toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" })} · ${r.summary.total}건`}
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
      </Stack>

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
