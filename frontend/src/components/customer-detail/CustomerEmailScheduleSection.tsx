import { Card, Chip, Stack, TextField, Typography } from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { updateCustomerEmailSchedule, type CustomerFull } from "@/api/customers";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

// ISO 요일 번호(1=월~7=일) — app/models/customers.py report_auto_send_days와 동일.
const DAYS: { iso: number; label: string }[] = [
  { iso: 1, label: "월" },
  { iso: 2, label: "화" },
  { iso: 3, label: "수" },
  { iso: 4, label: "목" },
  { iso: 5, label: "금" },
  { iso: 6, label: "토" },
  { iso: 7, label: "일" },
];

interface Props {
  customer: CustomerFull;
}

// 보고서 메일 자동발송 요일·시간(2026-09-14 사용자 지시) — app/scheduler.py의
// run_due_customer_emails가 이 설정을 그대로 읽어 실제로 매주 그 요일·시각에 신규 관심
// 공고 리포트를 생성해 report_recipient_emails로 보낸다. DataChannelsPage의
// ScheduleTimesEditor와 같은 원칙으로 값이 바뀌면 바로 저장한다(별도 "저장" 버튼 없음).
export function CustomerEmailScheduleSection({ customer }: Props) {
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [days, setDays] = useState<number[]>(customer.report_auto_send_days);
  const [time, setTime] = useState<string>(customer.report_auto_send_time ?? "");

  // 다른 화면(고객 정보 저장 등)이 ["customers-full"]을 무효화해도 이 섹션은 자기 자신을
  // 아직 손 안 댔으면 서버 값을 그대로 반영한다 — CustomerDetailPage.tsx의 동기화 원칙과 동일.
  useEffect(() => {
    setDays(customer.report_auto_send_days);
    setTime(customer.report_auto_send_time ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- customer.id 전환 시에만 재동기화
  }, [customer.id]);

  const mutation = useMutation({
    mutationFn: (schedule: { days: number[]; time: string | null }) =>
      updateCustomerEmailSchedule(customer.id, schedule),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers-full"] });
      notify("success", "메일 자동발송 설정을 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "메일 자동발송 설정 저장에 실패했습니다.")),
  });

  function commit(nextDays: number[], nextTime: string) {
    mutation.mutate({ days: nextDays, time: nextTime || null });
  }

  function toggleDay(iso: number) {
    const nextDays = days.includes(iso) ? days.filter((d) => d !== iso) : [...days, iso].sort((a, b) => a - b);
    setDays(nextDays);
    commit(nextDays, time);
  }

  function handleTimeBlur() {
    commit(days, time);
  }

  const isActive = days.length > 0 && !!time;

  return (
    <Card sx={{ p: 3 }}>
      <Typography variant="h3" sx={{ mb: 1 }}>
        보고서 메일 자동발송
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        선택한 요일·시각(한국 표준시)마다 신규 관심 공고 리포트를 자동 생성해 위 "보고서 수신자
        이메일"로 보냅니다. 신규 공고가 0건인 주는 발송하지 않습니다. 요일을 하나도 선택하지
        않으면(또는 시각 미설정) 자동발송이 꺼진 상태입니다 — "보고서 관리" 화면에서 수동으로
        생성·발송하는 것은 이 설정과 무관하게 계속 가능합니다.
      </Typography>

      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        {DAYS.map((d) => (
          <Chip
            key={d.iso}
            label={d.label}
            clickable
            color={days.includes(d.iso) ? "primary" : "default"}
            variant={days.includes(d.iso) ? "filled" : "outlined"}
            onClick={() => toggleDay(d.iso)}
          />
        ))}
      </Stack>

      <Stack direction="row" spacing={1.5} alignItems="center">
        <TextField
          size="small"
          type="time"
          label="발송 시각"
          value={time}
          onChange={(e) => setTime(e.target.value)}
          onBlur={handleTimeBlur}
          sx={{ minWidth: 160 }}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <Typography variant="body2" color={isActive ? "success.main" : "text.secondary"}>
          {isActive
            ? `매주 ${days.map((iso) => DAYS.find((d) => d.iso === iso)?.label).join(", ")}요일 ${time}에 자동발송`
            : "자동발송 꺼짐"}
        </Typography>
      </Stack>
    </Card>
  );
}
