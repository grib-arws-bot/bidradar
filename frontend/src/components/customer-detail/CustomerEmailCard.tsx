import { Button, Card, Chip, Divider, Stack, TextField, Typography } from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { type CustomerFull, toCustomerDraft, updateCustomer } from "@/api/customers";
import { generateReport, sendReport } from "@/api/reports";
import { CustomerEmailScheduleSection } from "@/components/customer-detail/CustomerEmailScheduleSection";
import { LoadingButton } from "@/components/LoadingButton";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

interface Props {
  customer: CustomerFull;
}

// 메일 발송(2026-09-15 신설) — 그동안 "고객 정보" 카드 안에 끼어 있던 "보고서 수신자
// 이메일"과 "보고서 메일 자동발송"을 메일 관련 기능으로 한데 모은 별도 카드(사용자 지시 —
// "보고서 수신자 이메일, 보고서 메일 자동발송을 묶어서 별도의 카드로 만들자"). 여기 더해
// "지금 발송" 버튼을 새로 추가해 관리자가 예정 시각과 무관하게 언제든 즉시 보낼 수 있게
// 한다(사용자 지시 — "이 카드 안에 지금 발송 버튼을 만들어서 관리자가 언제든 보낼 수 있게").
//
// 수신자 이메일은 "고객 정보" 카드의 CustomerDraft(수동 "저장" 버튼)와 달리 이 카드 자체에서
// 즉시 저장한다 — toCustomerDraft(customer)로 서버의 최신 값을 그대로 가져와 수신자 목록만
// 바꿔 PATCH하므로, "고객 정보" 카드에서 편집 중인(아직 저장 안 한) 다른 필드를 건드리지
// 않는다.
export function CustomerEmailCard({ customer }: Props) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [recipientInput, setRecipientInput] = useState("");

  const recipientMutation = useMutation({
    mutationFn: (emails: string[]) => updateCustomer(customer.id, { ...toCustomerDraft(customer), report_recipient_emails: emails }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers-full"] });
      notify("success", "보고서 수신자를 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "보고서 수신자 저장에 실패했습니다.")),
  });

  function addRecipient() {
    const email = recipientInput.trim();
    if (!email || customer.report_recipient_emails.includes(email)) return;
    recipientMutation.mutate([...customer.report_recipient_emails, email]);
    setRecipientInput("");
  }

  function removeRecipient(email: string) {
    recipientMutation.mutate(customer.report_recipient_emails.filter((e) => e !== email));
  }

  // "보고서 지금 생성 후 발송"(2026-09-15 버튼명 변경 — 무엇을 하는 버튼인지 이름에서 바로
  // 알 수 있게) — 최신 관심 공고로 보고서를 새로 생성한 뒤 곧바로 발송한다. 예정된 자동발송
  // 시각(위 스케줄)과 무관하게 관리자가 임의 시점에 실행하는 것이므로, run_due_customer_emails
  // 와 달리 신규 매칭 0건이어도 발송을 막지 않는다("보고서 관리" 화면의 수동 발송과 같은
  // 원칙 — 관리자가 명시적으로 누른 동작은 그대로 실행).
  const sendNowMutation = useMutation({
    mutationFn: async () => {
      const report = await generateReport(customer.id);
      return sendReport(customer.id, report.id);
    },
    onSuccess: (result) => notify("success", `${result.sent_to.length}명에게 즉시 발송했습니다.`),
    onError: (error) => notify("error", apiErrorMessage(error, "메일 발송에 실패했습니다.")),
  });

  const hasRecipients = customer.report_recipient_emails.length > 0;

  return (
    <Card sx={{ p: 3 }}>
      <Typography variant="h3" sx={{ mb: 2 }}>
        메일 발송
      </Typography>
      <Stack spacing={2}>
        <Typography variant="subtitle2">보고서 수신자 이메일</Typography>
        <Stack direction="row" spacing={1}>
          <TextField
            size="small"
            placeholder="이메일 입력 후 Enter"
            value={recipientInput}
            onChange={(e) => setRecipientInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addRecipient())}
            disabled={recipientMutation.isPending}
            fullWidth
          />
          <Button variant="outlined" onClick={addRecipient} disabled={recipientMutation.isPending}>
            추가
          </Button>
        </Stack>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {customer.report_recipient_emails.map((email) => (
            <Chip
              key={email}
              label={email}
              size="small"
              onDelete={() => removeRecipient(email)}
              disabled={recipientMutation.isPending}
            />
          ))}
        </Stack>

        <Divider />

        <CustomerEmailScheduleSection customer={customer} />

        <Divider />

        <Stack direction="row" spacing={2} alignItems="center">
          <LoadingButton
            variant="contained"
            loading={sendNowMutation.isPending}
            loadingText="발송 중..."
            disabled={!hasRecipients}
            onClick={() => sendNowMutation.mutate()}
          >
            보고서 지금 생성 후 발송
          </LoadingButton>
          <Typography variant="body2" color="text.secondary">
            {hasRecipients
              ? "최신 관심 공고로 보고서를 새로 생성해 위 수신자에게 즉시 보냅니다."
              : "수신자 이메일을 먼저 등록해야 발송할 수 있습니다."}
          </Typography>
        </Stack>
      </Stack>
    </Card>
  );
}
