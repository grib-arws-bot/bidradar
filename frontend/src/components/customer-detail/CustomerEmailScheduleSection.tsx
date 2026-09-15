import { Chip, Stack, TextField, Typography } from "@mui/material";
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

// source.schedule_times(DataChannelsPage.tsx)와 같은 상한 — app/services/customer_management.py
// MAX_EMAIL_SCHEDULE_TIMES와 맞춤.
const MAX_TIMES = 3;

function fillSlots(value: string[]): string[] {
  return [...value, ...Array(MAX_TIMES - value.length).fill("")].slice(0, MAX_TIMES);
}

interface Props {
  customer: CustomerFull;
}

// 보고서 메일 자동발송 요일·시각(2026-09-14 도입, 2026-09-15 시각 복수 지정으로 확장 —
// "메일 발송 시점은 다수개를 지정할 수 있어야 한다") — app/scheduler.py의
// run_due_customer_emails가 이 설정을 그대로 읽어 실제로 매주 그 요일·(여러) 시각마다
// 신규 관심 공고 리포트를 자동 생성해 report_recipient_emails로 보낸다. DataChannelsPage의
// ScheduleTimesEditor와 같은 원칙(값이 바뀌면 바로 저장, 별도 "저장" 버튼 없음)에 슬롯 3개
// 방식까지 그대로 맞췄다 — 단 여기서는 days와 times를 한 번에 같이 저장한다(API가
// {days, times} 하나로 묶여 있어서, 날짜 칩만 바꿔도 지금 화면에 있는 시각들을 함께 보낸다).
//
// 2026-09-15 — 사용자 지시("메일 발송 기능을 모아줘")로 별도 카드에서 "고객 정보" 카드 안
// "보고서 수신자 이메일" 바로 아래 서브섹션으로 옮김(CustomerDetailPage.tsx) — 메일 관련
// 설정(수신자·자동발송 요일/시각)을 한 곳에서 보이게 한다. 그래서 여기선 독립 Card를 두르지
// 않고 형제 섹션("담당자" 등)과 같은 subtitle2 헤더 스타일만 쓴다.
export function CustomerEmailScheduleSection({ customer }: Props) {
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [days, setDays] = useState<number[]>(customer.report_auto_send_days);
  const [timeDrafts, setTimeDrafts] = useState<string[]>(() => fillSlots(customer.report_auto_send_times));

  const mutation = useMutation({
    mutationFn: (schedule: { days: number[]; times: string[] }) =>
      updateCustomerEmailSchedule(customer.id, schedule),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers-full"] });
      notify("success", "메일 자동발송 설정을 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "메일 자동발송 설정 저장에 실패했습니다.")),
  });

  // 다른 화면(고객 정보 저장 등)이 ["customers-full"]을 무효화해도 이 섹션은 자기 자신을
  // 아직 손 안 댔으면(mutation이 안 도는 중이면) 서버 값을 그대로 반영한다 —
  // CustomerDetailPage.tsx의 동기화 원칙과 동일.
  useEffect(() => {
    if (mutation.isPending) return;
    setDays(customer.report_auto_send_days);
    setTimeDrafts(fillSlots(customer.report_auto_send_times));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- customer.id 전환 시에만 재동기화
  }, [customer.id]);

  function commit(nextDays: number[], nextTimeDrafts: string[]) {
    mutation.mutate({ days: nextDays, times: nextTimeDrafts.filter(Boolean) });
  }

  function toggleDay(iso: number) {
    const nextDays = days.includes(iso) ? days.filter((d) => d !== iso) : [...days, iso].sort((a, b) => a - b);
    setDays(nextDays);
    commit(nextDays, timeDrafts);
  }

  function handleTimeBlur(index: number, raw: string) {
    const next = [...timeDrafts];
    next[index] = raw;
    setTimeDrafts(next);
    commit(days, next);
  }

  const activeTimes = timeDrafts.filter(Boolean);
  const isActive = days.length > 0 && activeTimes.length > 0;

  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle2">보고서 메일 자동발송</Typography>
      <Typography variant="body2" color="text.secondary">
        선택한 요일·시각(한국 표준시, 최대 {MAX_TIMES}개)마다 신규 관심 공고 리포트를 자동
        생성해 위 "보고서 수신자 이메일"로 보냅니다. 신규 공고가 0건인 주는 발송하지 않습니다.
        요일을 하나도 선택하지 않으면(또는 시각 미설정) 자동발송이 꺼진 상태입니다 — "보고서
        관리" 화면에서 수동으로 생성·발송하는 것은 이 설정과 무관하게 계속 가능합니다.
      </Typography>

      <Stack direction="row" spacing={1}>
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

      <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
        {timeDrafts.map((draft, i) => (
          <TextField
            key={i}
            size="small"
            type="time"
            label={`발송 시각 ${i + 1}`}
            value={draft}
            disabled={mutation.isPending}
            onChange={(e) => {
              const next = [...timeDrafts];
              next[i] = e.target.value;
              setTimeDrafts(next);
            }}
            onBlur={(e) => handleTimeBlur(i, e.target.value)}
            sx={{ minWidth: 160 }}
            slotProps={{ inputLabel: { shrink: true } }}
          />
        ))}
        <Typography variant="body2" color={isActive ? "success.main" : "text.secondary"}>
          {isActive
            ? `매주 ${days.map((iso) => DAYS.find((d) => d.iso === iso)?.label).join(", ")}요일 ${activeTimes.join(", ")}에 자동발송`
            : "자동발송 꺼짐"}
        </Typography>
      </Stack>
    </Stack>
  );
}
