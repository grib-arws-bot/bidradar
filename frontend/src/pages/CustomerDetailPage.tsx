import ArrowBackIcon from "@mui/icons-material/ArrowBackOutlined";
import {
  Box,
  Button,
  Card,
  Chip,
  CircularProgress,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchCustomersFull, updateCustomer, type CustomerDraft, type CustomerFull } from "@/api/customers";
import { CustomerDocumentsSection } from "@/components/customer-detail/CustomerDocumentsSection";
import { CustomerEmailScheduleSection } from "@/components/customer-detail/CustomerEmailScheduleSection";
import { CustomerInterestSection } from "@/components/customer-detail/CustomerInterestSection";
import { LoadingButton } from "@/components/LoadingButton";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

function toDraft(c: CustomerFull): CustomerDraft {
  const {
    id: _id,
    profile_summary_md: _md,
    profile_summarized_at: _at,
    profile_summary_cost: _cost,
    report_auto_send_days: _days,
    report_auto_send_time: _time,
    ...draft
  } = c;
  return draft;
}

// 고객 상세(2026-09-05 메뉴 재정리) — 담당자·소개서 파일·프로필 요약·관심주제를 한 화면에
// 모았다("고객 관리" 목록에서 행을 클릭하면 여기로 온다). 리포트 생성·발송은 별도
// "보고서 관리" 메뉴로 분리(고객마다 여러 리포트를 다루는 화면이라 목록형이 더 맞음).
export function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const customerId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const customersQuery = useQuery({ queryKey: ["customers-full"], queryFn: fetchCustomersFull });
  const customer = (customersQuery.data ?? []).find((c) => c.id === customerId);

  const [draft, setDraft] = useState<CustomerDraft | null>(null);
  const [recipientInput, setRecipientInput] = useState("");

  // 2026-09-12 수정 — customer는 ["customers-full"]이 무효화될 때마다(파일 업로드·참고 URL
  // 추가·프로필 요약 등 이 페이지 안의 다른 어떤 동작이든) 새 참조로 바뀌는데, 이 effect가
  // 그때마다 draft를 무조건 덮어써서 "고객 정보" 폼을 편집하다가 다른 섹션에서 버튼을 누르면
  // 저장 전 내용이 조용히 사라졌다(CustomerInterestSection.tsx의 2026-09-10 버그와 같은
  // 계열). 마지막으로 동기화한 서버값 그대로 손 안 댔을 때만(또는 고객 전환 시) 다시 채운다.
  const lastSyncedRef = useRef<{ customerId: number; draft: CustomerDraft } | null>(null);
  useEffect(() => {
    if (!customer) return;
    const serverDraft = toDraft(customer);
    const last = lastSyncedRef.current;
    const isCustomerSwitch = last?.customerId !== customerId;
    const isUntouchedSinceLastSync = last?.customerId === customerId && JSON.stringify(draft) === JSON.stringify(last.draft);
    if (isCustomerSwitch || isUntouchedSinceLastSync) {
      setDraft(serverDraft);
      lastSyncedRef.current = { customerId, draft: serverDraft };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- draft는 비교용으로만 읽는다
  }, [customer, customerId]);

  // onError가 없어서 저장이 실패해도 아무 표시가 없던 문제(2026-09-07 발견) — 성공·실패
  // 모두 토스트로 알린다.
  const updateMutation = useMutation({
    mutationFn: (d: CustomerDraft) => updateCustomer(customerId, d),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers-full"] });
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      notify("success", "고객 정보를 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "고객 정보 저장에 실패했습니다.")),
  });

  function update(patch: Partial<CustomerDraft>) {
    setDraft((prev) => (prev ? { ...prev, ...patch } : prev));
  }

  function addRecipient() {
    if (!draft) return;
    const email = recipientInput.trim();
    if (!email || draft.report_recipient_emails.includes(email)) return;
    update({ report_recipient_emails: [...draft.report_recipient_emails, email] });
    setRecipientInput("");
  }

  if (customersQuery.isLoading || !draft) {
    return <CircularProgress />;
  }
  if (!customer) {
    return (
      <Box>
        <Typography>고객을 찾을 수 없습니다.</Typography>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/customers")} sx={{ mt: 2 }}>
          고객 목록으로
        </Button>
      </Box>
    );
  }

  return (
    <Stack spacing={3} sx={{ maxWidth: 960 }}>
      <Stack direction="row" alignItems="center" spacing={1.5}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/customers")}>
          고객 목록
        </Button>
        <Typography variant="h2">{customer.name}</Typography>
        <Chip
          size="small"
          label={draft.plan_tier === "internal" ? "그립 자신" : draft.plan_tier}
          color={draft.plan_tier === "internal" ? "default" : "primary"}
          variant="outlined"
        />
      </Stack>

      <Card sx={{ p: 3 }}>
        <Typography variant="h3" sx={{ mb: 2 }}>
          고객 정보
        </Typography>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1.5}>
            <TextField label="고객명" value={draft.name} onChange={(e) => update({ name: e.target.value })} fullWidth />
            <TextField
              select
              label="등급"
              value={draft.plan_tier}
              disabled={draft.plan_tier === "internal"}
              onChange={(e) => update({ plan_tier: e.target.value as CustomerDraft["plan_tier"] })}
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="standard">standard</MenuItem>
              <MenuItem value="premium">premium</MenuItem>
              {draft.plan_tier === "internal" && <MenuItem value="internal">internal(그립 자신)</MenuItem>}
            </TextField>
          </Stack>

          <Typography variant="subtitle2">담당자</Typography>
          <Stack direction="row" spacing={1.5}>
            <TextField
              size="small"
              label="이름"
              value={draft.contact_name ?? ""}
              onChange={(e) => update({ contact_name: e.target.value })}
              fullWidth
            />
            <TextField
              size="small"
              label="직위"
              value={draft.contact_title ?? ""}
              onChange={(e) => update({ contact_title: e.target.value })}
              fullWidth
            />
          </Stack>
          <Stack direction="row" spacing={1.5}>
            <TextField
              size="small"
              label="전화번호"
              value={draft.contact_phone ?? ""}
              onChange={(e) => update({ contact_phone: e.target.value })}
              fullWidth
            />
            <TextField
              size="small"
              label="이메일"
              value={draft.contact_email ?? ""}
              onChange={(e) => update({ contact_email: e.target.value })}
              fullWidth
            />
          </Stack>

          <Typography variant="subtitle2">보고서 수신자 이메일</Typography>
          <Stack direction="row" spacing={1}>
            <TextField
              size="small"
              placeholder="이메일 입력 후 Enter"
              value={recipientInput}
              onChange={(e) => setRecipientInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addRecipient())}
              fullWidth
            />
            <Button variant="outlined" onClick={addRecipient}>
              추가
            </Button>
          </Stack>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {draft.report_recipient_emails.map((email) => (
              <Chip
                key={email}
                label={email}
                size="small"
                onDelete={() =>
                  update({ report_recipient_emails: draft.report_recipient_emails.filter((e) => e !== email) })
                }
              />
            ))}
          </Stack>

          <FormControlLabel
            control={<Switch checked={draft.active} onChange={(e) => update({ active: e.target.checked })} />}
            label="활성"
          />

          <Stack direction="row" spacing={2} alignItems="center">
            <LoadingButton
              variant="contained"
              loading={updateMutation.isPending}
              loadingText="저장 중..."
              disabled={!draft.name.trim()}
              onClick={() => updateMutation.mutate(draft)}
            >
              저장
            </LoadingButton>
          </Stack>
        </Stack>
      </Card>

      <CustomerDocumentsSection customer={customer} />
      <CustomerEmailScheduleSection customer={customer} />
      <CustomerInterestSection customerId={customer.id} />
    </Stack>
  );
}
