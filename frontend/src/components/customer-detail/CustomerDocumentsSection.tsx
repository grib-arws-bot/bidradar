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
  updateCustomerProfileSummary,
  uploadCustomerDocuments,
  type CustomerFull,
} from "@/api/customers";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

const SELECTABLE_MODELS: { value: LlmModel; label: string }[] = [
  { value: "haiku", label: "Haiku (저렴)" },
  { value: "sonnet", label: "Sonnet (기본, 고품질)" },
];

function formatSize(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)}MB` : `${(bytes / 1024).toFixed(0)}KB`;
}

// 소개서 파일(다중 업로드, DB 바이너리 저장) + 고객 프로필 요약(AI, "B로 하자" 결정 —
// 소개서를 매번 LLM에 넣지 않고 한 번 요약해 캐싱, 재요약은 관리자가 수동으로만).
export function CustomerDocumentsSection({ customer }: { customer: CustomerFull }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const customerId = customer.id;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [profileDialogOpen, setProfileDialogOpen] = useState(false);
  const [profileModel, setProfileModel] = useState<LlmModel>("sonnet");
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");

  const documentsQuery = useQuery({
    queryKey: ["customer-documents", customerId],
    queryFn: () => fetchCustomerDocuments(customerId),
  });

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => uploadCustomerDocuments(customerId, files),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customer-documents", customerId] });
      notify("success", "파일을 업로드했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "파일 업로드에 실패했습니다.")),
  });

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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers-full"] });
      notify("success", "프로필 요약을 생성했습니다.");
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
      <Button
        size="small"
        variant="outlined"
        startIcon={<UploadFileIcon />}
        disabled={uploadMutation.isPending}
        onClick={() => fileInputRef.current?.click()}
        sx={{ mb: 1 }}
      >
        파일 추가(다중 선택 가능)
      </Button>
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
                  <IconButton size="small" onClick={() => deleteDocMutation.mutate(doc.id)}>
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
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

      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 3, mb: 1 }}>
        <Typography variant="h3">고객 프로필 요약(AI) — 전략 수립 참고자료</Typography>
        <Stack direction="row" spacing={1}>
          {!editing && (
            <Button size="small" startIcon={<EditOutlinedIcon />} onClick={startEditing}>
              {customer.profile_summary_md ? "편집" : "직접 작성"}
            </Button>
          )}
          <Button
            size="small"
            variant="outlined"
            startIcon={<AutoAwesomeOutlinedIcon />}
            disabled={summarizeMutation.isPending || editing}
            onClick={() => setProfileDialogOpen(true)}
          >
            {summarizeMutation.isPending ? "요약 중..." : customer.profile_summarized_at ? "재요약" : "요약 생성"}
          </Button>
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
            <Button
              size="small"
              variant="contained"
              disabled={updateSummaryMutation.isPending}
              onClick={() => updateSummaryMutation.mutate(editText)}
            >
              저장
            </Button>
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
          아직 요약이 없습니다. 소개서 파일을 업로드한 뒤 "요약 생성"을 누르거나, "직접 작성"으로
          바로 입력할 수 있습니다.
        </Typography>
      )}

      <Dialog open={profileDialogOpen} onClose={() => setProfileDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{customer.profile_summarized_at ? "고객 프로필 재요약" : "고객 프로필 요약 생성"}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            LLM 호출 비용이 발생합니다. 소개서 파일 전체를 다시 읽어 요약하며, 이후 보고서
            AI 코멘트 생성의 기반 자료로 쓰입니다
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
