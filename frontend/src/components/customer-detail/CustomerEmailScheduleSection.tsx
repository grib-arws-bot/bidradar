import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import { Button, IconButton, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { type CustomerFull, type EmailScheduleEntry, updateCustomerEmailSchedule } from "@/api/customers";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

// ISO 요일 번호(1=월~7=일) — app/models/customers.py report_auto_send_schedule와 동일.
const DAYS: { iso: number; label: string }[] = [
  { iso: 1, label: "월" },
  { iso: 2, label: "화" },
  { iso: 3, label: "수" },
  { iso: 4, label: "목" },
  { iso: 5, label: "금" },
  { iso: 6, label: "토" },
  { iso: 7, label: "일" },
];

const MAX_ENTRIES = 3;
const dayLabel = (iso: number) => DAYS.find((d) => d.iso === iso)?.label ?? "?";

interface Props {
  customer: CustomerFull;
}

// 보고서 메일 자동발송 (요일,시각) 쌍(2026-09-14 도입, 2026-09-15 두 차례 재설계).
//
// 1차 설계(요일 목록 + 시각 목록을 따로 받아 카르테시안 곱으로 실행)는 사용자가 실제로
// 원한 "월 13시, 목 14시"처럼 요일마다 다른 시각을 지정하는 걸 표현할 수 없었다 — "월,목"에
// "13시,14시"를 주면 4가지 조합 전부가 발송 대상이 돼버림. 그래서 (요일,시각) 쌍 하나하나를
// 행으로 추가·삭제하는 방식(최대 3개, source.schedule_times와 동일 상한)으로 다시 바꿨다.
// 값이 바뀌면 바로 저장한다(별도 "저장" 버튼 없음, DataChannelsPage의 ScheduleTimesEditor와
// 같은 원칙).
//
// 2026-09-15 — "메일 발송 기능을 모아줘" 요청으로 CustomerEmailCard(신규) 안의 서브섹션으로
// 옮김 — 독립 Card를 두르지 않고 형제 섹션과 같은 subtitle2 헤더 스타일만 쓴다.
export function CustomerEmailScheduleSection({ customer }: Props) {
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [schedule, setSchedule] = useState<EmailScheduleEntry[]>(customer.report_auto_send_schedule);

  const mutation = useMutation({
    mutationFn: (next: EmailScheduleEntry[]) => updateCustomerEmailSchedule(customer.id, next),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers-full"] });
      notify("success", "메일 자동발송 설정을 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "메일 자동발송 설정 저장에 실패했습니다.")),
  });

  // 다른 화면이 ["customers-full"]을 무효화해도 이 섹션은 자기 자신을 아직 손 안 댔으면
  // (mutation이 안 도는 중이면) 서버 값을 그대로 반영한다.
  useEffect(() => {
    if (mutation.isPending) return;
    setSchedule(customer.report_auto_send_schedule);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- customer.id 전환 시에만 재동기화
  }, [customer.id]);

  function commit(next: EmailScheduleEntry[]) {
    setSchedule(next);
    mutation.mutate(next);
  }

  function addRow() {
    if (schedule.length >= MAX_ENTRIES) return;
    // 아직 안 쓰인 요일부터 기본값으로 제안(모든 요일이 이미 있으면 월요일로 대체).
    const unusedDay = DAYS.find((d) => !schedule.some((s) => s.day === d.iso))?.iso ?? 1;
    commit([...schedule, { day: unusedDay, time: "09:00" }]);
  }

  function updateRow(index: number, patch: Partial<EmailScheduleEntry>) {
    const next = schedule.map((entry, i) => (i === index ? { ...entry, ...patch } : entry));
    setSchedule(next); // 입력 중엔 로컬만 갱신 — 시각 필드는 onBlur에서, 요일은 즉시 commit
  }

  function removeRow(index: number) {
    commit(schedule.filter((_, i) => i !== index));
  }

  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle2">보고서 메일 자동발송</Typography>
      <Typography variant="body2" color="text.secondary">
        지정한 요일·시각(한국 표준시, 최대 {MAX_ENTRIES}개)마다 신규 관심 공고 리포트를 자동
        생성해 위 "보고서 수신자 이메일"로 보냅니다. 요일마다 다른 시각을 지정할 수 있습니다
        (예: 월 13:00, 목 14:00). 신규 공고가 0건인 주는 발송하지 않습니다.
      </Typography>

      <Stack spacing={1}>
        {schedule.map((entry, i) => (
          <Stack key={i} direction="row" spacing={1.5} alignItems="center">
            <TextField
              select
              size="small"
              label="요일"
              value={entry.day}
              disabled={mutation.isPending}
              onChange={(e) => commit(schedule.map((s, idx) => (idx === i ? { ...s, day: Number(e.target.value) } : s)))}
              sx={{ minWidth: 100 }}
            >
              {DAYS.map((d) => (
                <MenuItem key={d.iso} value={d.iso}>
                  {d.label}요일
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              type="time"
              label="시각"
              value={entry.time}
              disabled={mutation.isPending}
              onChange={(e) => updateRow(i, { time: e.target.value })}
              onBlur={() => commit(schedule)}
              sx={{ minWidth: 140 }}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <IconButton size="small" onClick={() => removeRow(i)} disabled={mutation.isPending} aria-label="삭제">
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Stack>
        ))}
      </Stack>

      <Stack direction="row" spacing={1.5} alignItems="center">
        <Button size="small" variant="outlined" onClick={addRow} disabled={mutation.isPending || schedule.length >= MAX_ENTRIES}>
          요일·시각 추가
        </Button>
        <Typography variant="body2" color={schedule.length > 0 ? "success.main" : "text.secondary"}>
          {schedule.length > 0
            ? `매주 ${schedule.map((s) => `${dayLabel(s.day)} ${s.time}`).join(", ")}에 자동발송`
            : "자동발송 꺼짐"}
        </Typography>
      </Stack>
    </Stack>
  );
}
