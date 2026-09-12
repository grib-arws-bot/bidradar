import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DownloadIcon from "@mui/icons-material/DownloadOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import UploadFileIcon from "@mui/icons-material/UploadFileOutlined";
import {
  Alert,
  Box,
  Button,
  Card,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import type { LlmModel } from "@/api/analysis";
import {
  customerDocumentDownloadUrl,
  deleteCustomerDocument,
  fetchCustomerDocuments,
  summarizeCustomerProfile,
  updateCustomer,
  updateCustomerProfileSummary,
  uploadCustomerDocuments,
  type CustomerFull,
} from "@/api/customers";
import { LoadingButton, LoadingIconButton } from "@/components/LoadingButton";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

const SELECTABLE_MODELS: { value: LlmModel; label: string }[] = [
  { value: "haiku", label: "Haiku (저렴)" },
  { value: "sonnet", label: "Sonnet (기본, 고품질)" },
];

function formatSize(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)}MB` : `${(bytes / 1024).toFixed(0)}KB`;
}

// "AI 고객 분석"(2026-09-11, "소개서 파일"에서 개명) — 소개서 파일(다중 업로드, DB 바이너리
// 저장) + 참고 URL(customer.reference_urls) + 고객 프로필 요약(AI, "B로 하자" 결정 —
// 파일·URL을 매번 LLM에 넣지 않고 한 번 요약해 캐싱, 재요약은 관리자가 수동으로만).
export function CustomerDocumentsSection({ customer }: { customer: CustomerFull }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const customerId = customer.id;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [profileDialogOpen, setProfileDialogOpen] = useState(false);
  const [profileModel, setProfileModel] = useState<LlmModel>("sonnet");
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [urlInput, setUrlInput] = useState("");

  const documentsQuery = useQuery({
    queryKey: ["customer-documents", customerId],
    queryFn: () => fetchCustomerDocuments(customerId),
  });

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => uploadCustomerDocuments(customerId, files),
    onSuccess: ({ documents, errors }, files) => {
      queryClient.setQueryData(["customer-documents", customerId], documents);
      const succeededCount = files.length - errors.length;
      if (errors.length > 0) notify("error", `${errors.length}개 파일 업로드 실패: ${errors.join(" / ")}`);
      if (succeededCount > 0) notify("success", `파일 ${succeededCount}개를 업로드했습니다.`);
    },
    onError: (error) => notify("error", apiErrorMessage(error, "파일 업로드에 실패했습니다.")),
  });

  // 참고 URL 목록은 customer.reference_urls(JSONB 배열)에 저장 — 다른 고객 정보 필드(이름·
  // 등급 등)는 그대로 두고 이 필드만 바꿔서 저장한다(2026-09-11, "AI 고객 분석"에 URL 입력
  // 추가). 파일 업로드처럼 추가·삭제 즉시 반영(위쪽 "고객 정보" 카드의 "저장" 버튼과 무관).
  const updateUrlsMutation = useMutation({
    mutationFn: (urls: string[]) =>
      updateCustomer(customerId, {
        name: customer.name,
        plan_tier: customer.plan_tier,
        contact_email: customer.contact_email,
        contact_name: customer.contact_name,
        contact_title: customer.contact_title,
        contact_phone: customer.contact_phone,
        report_recipient_emails: customer.report_recipient_emails,
        reference_urls: urls,
        active: customer.active,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["customers-full"] }),
    onError: (error) => notify("error", apiErrorMessage(error, "참고 URL 저장에 실패했습니다.")),
  });

  function addUrl() {
    const url = urlInput.trim();
    if (!url || customer.reference_urls.includes(url)) return;
    updateUrlsMutation.mutate([...customer.reference_urls, url]);
    setUrlInput("");
  }

  function removeUrl(url: string) {
    updateUrlsMutation.mutate(customer.reference_urls.filter((u) => u !== url));
  }

  const deleteDocMutation = useMutation({
    mutationFn: (documentId: number) => deleteCustomerDocument(customerId, documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customer-documents", customerId] });
      notify("success", "파일을 삭제했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "파일 삭제에 실패했습니다.")),
  });

  const summarizeMutation = useMutation({
    mutationFn: (model: LlmModel) => summarizeCustomerProfile(customerId, model),
    onSuccess: ({ failed_urls, auto_set_topics }) => {
      queryClient.invalidateQueries({ queryKey: ["customers-full"] });
      notify("success", "프로필 요약을 생성했습니다.");
      if (failed_urls.length > 0) notify("error", `${failed_urls.length}개 URL을 가져오지 못했습니다: ${failed_urls.join(" / ")}`);
      if (auto_set_topics.length > 0) {
        queryClient.invalidateQueries({ queryKey: ["interest-profile", customerId] });
        notify("success", `관심주제를 자동 설정했습니다: ${auto_set_topics.join(", ")}`);
      }
    },
    onError: (error) => notify("error", apiErrorMessage(error, "요약 생성에 실패했습니다.")),
  });

  const updateSummaryMutation = useMutation({
    mutationFn: (summaryMd: string) => updateCustomerProfileSummary(customerId, summaryMd),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers-full"] });
      setEditing(false);
      notify("success", "프로필 요약을 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "프로필 요약 저장에 실패했습니다.")),
  });

  function confirmSummarize() {
    setProfileDialogOpen(false);
    summarizeMutation.mutate(profileModel);
  }

  function startEditing() {
    setEditText(customer.profile_summary_md ?? "");
    setEditing(true);
  }

  return (
    <Card sx={{ p: 3 }}>
      <Typography variant="h3" sx={{ mb: 1.5 }}>
        AI 고객 분석
      </Typography>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        소개서 파일
      </Typography>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length > 0) uploadMutation.mutate(files);
          e.target.value = "";
        }}
      />
      <LoadingButton
        size="small"
        variant="outlined"
        startIcon={<UploadFileIcon />}
        loading={uploadMutation.isPending}
        loadingText="업로드 중..."
        onClick={() => fileInputRef.current?.click()}
        sx={{ mb: 1 }}
      >
        파일 추가(다중 선택 가능)
      </LoadingButton>
      <List dense disablePadding>
        {(documentsQuery.data ?? []).map((doc) => (
          <ListItem
            key={doc.id}
            disableGutters
            secondaryAction={
              <Stack direction="row">
                <Tooltip title="다운로드">
                  <IconButton size="small" component="a" href={customerDocumentDownloadUrl(customerId, doc.id)}>
                    <DownloadIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="삭제">
                  <LoadingIconButton
                    size="small"
                    loading={deleteDocMutation.isPending && deleteDocMutation.variables === doc.id}
                    onClick={() => deleteDocMutation.mutate(doc.id)}
                  >
                    <DeleteOutlineIcon fontSize="small" />
                  </LoadingIconButton>
                </Tooltip>
              </Stack>
            }
          >
            <ListItemText primary={doc.filename} secondary={formatSize(doc.size_bytes)} />
          </ListItem>
        ))}
        {(documentsQuery.data ?? []).length === 0 && (
          <Typography variant="body2" color="text.secondary">
            업로드된 파일이 없습니다.
          </Typography>
        )}
      </List>

      <Typography variant="subtitle2" sx={{ mt: 2 }}>
        참고 URL
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
        요약 시 같은 도메인 내 다른 페이지도 함께 분석합니다(게시판류는 목록만 보고 더 들어가지 않음).
      </Typography>
      <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
        <TextField
          size="small"
          placeholder="URL 입력 후 Enter"
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addUrl())}
          fullWidth
        />
        <LoadingButton variant="outlined" loading={updateUrlsMutation.isPending} loadingText="추가 중..." onClick={addUrl}>
          추가
        </LoadingButton>
      </Stack>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
        {customer.reference_urls.map((url) => (
          <Chip key={url} label={url} size="small" onDelete={() => removeUrl(url)} />
        ))}
        {customer.reference_urls.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            등록된 URL이 없습니다.
          </Typography>
        )}
      </Stack>

      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 3, mb: 1 }}>
        <Typography variant="h3">고객 프로필 요약(AI) — 전략 수립 참고자료</Typography>
        <Stack direction="row" spacing={1}>
          {!editing && (
            <Button size="small" startIcon={<EditOutlinedIcon />} onClick={startEditing}>
              {customer.profile_summary_md ? "편집" : "직접 작성"}
            </Button>
          )}
          <LoadingButton
            size="small"
            variant="outlined"
            startIcon={<AutoAwesomeOutlinedIcon />}
            loading={summarizeMutation.isPending}
            loadingText="요약 중..."
            disabled={editing}
            onClick={() => setProfileDialogOpen(true)}
          >
            {customer.profile_summarized_at ? "재요약" : "요약 생성"}
          </LoadingButton>
        </Stack>
      </Stack>
      {editing ? (
        <Stack spacing={1}>
          <TextField
            multiline
            fullWidth
            minRows={10}
            maxRows={24}
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            placeholder={"## 회사 개요\n- ...\n\n## 주요 제품/서비스\n- ..."}
            slotProps={{ input: { sx: { fontFamily: "monospace", fontSize: 13 } } }}
          />
          <Stack direction="row" spacing={1}>
            <LoadingButton
              size="small"
              variant="contained"
              loading={updateSummaryMutation.isPending}
              loadingText="저장 중..."
              onClick={() => updateSummaryMutation.mutate(editText)}
            >
              저장
            </LoadingButton>
            <Button size="small" onClick={() => setEditing(false)}>
              취소
            </Button>
          </Stack>
        </Stack>
      ) : customer.profile_summary_md ? (
        <Box sx={{ maxHeight: 260, overflowY: "auto", bgcolor: "action.hover", borderRadius: 1, p: 1.5 }}>
          {customer.profile_summarized_at && (
            <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 0.5 }}>
              {new Date(customer.profile_summarized_at).toLocaleString("ko-KR")} AI 생성 · 누적 비용 $
              {customer.profile_summary_cost.toFixed(4)}
            </Typography>
          )}
          <Typography variant="body2" component="pre" sx={{ whiteSpace: "pre-wrap", fontFamily: "inherit", m: 0 }}>
            {customer.profile_summary_md}
          </Typography>
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary">
          아직 요약이 없습니다. 소개서 파일을 업로드하거나 참고 URL을 등록한 뒤 "요약 생성"을
          누르거나, "직접 작성"으로 바로 입력할 수 있습니다.
        </Typography>
      )}

      <Dialog open={profileDialogOpen} onClose={() => setProfileDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{customer.profile_summarized_at ? "고객 프로필 재요약" : "고객 프로필 요약 생성"}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            LLM 호출 비용이 발생합니다. 소개서 파일과 참고 URL 전체를 다시 읽어 요약하며,
            이후 보고서 AI 코멘트 생성의 기반 자료로 쓰입니다
            {customer.profile_summarized_at ? " — 재요약하면 기존 요약이 덮어써집니다." : "."}
          </Alert>
          <RadioGroup value={profileModel} onChange={(e) => setProfileModel(e.target.value as LlmModel)}>
            {SELECTABLE_MODELS.map((m) => (
              <FormControlLabel key={m.value} value={m.value} control={<Radio />} label={m.label} />
            ))}
          </RadioGroup>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setProfileDialogOpen(false)}>취소</Button>
          <Button variant="contained" onClick={confirmSummarize}>
            확인
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}
