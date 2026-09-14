import PlayArrowIcon from "@mui/icons-material/PlayArrowOutlined";
import {
  Box,
  Button,
  Card,
  Chip,
  CircularProgress,
  MenuItem,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  collectNow,
  fetchSources,
  updateActive,
  updateAutoAnalyze,
  updateAutoExtract,
  updateScheduleTimes,
  type SourceRow,
} from "@/api/sources";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

const NOTICE_TYPES: SourceRow["notice_type"][] = ["공공입찰", "정부지원"];
const MAX_SCHEDULE_SLOTS = 3;

function fillSlots(value: string[]): string[] {
  return [...value, ...Array(MAX_SCHEDULE_SLOTS - value.length).fill("")].slice(0, MAX_SCHEDULE_SLOTS);
}

// "HH:MM"이든 한 자리 시/분("9:0")이든 받아 00:00~23:59 범위인지 검사하고, 통과하면 항상
// 두 자리로 맞춘 표준형("09:00")을 돌려준다. null이면 형식·범위가 잘못된 것.
// (2026-09-07 발견 — 두 자리 형식만 허용하던 정규식이 "9:00" 같은 입력을 조용히 거부해서
// IRIS 채널의 업데이트 시간이 저장 안 되는 것처럼 보이는 원인이었다.)
function normalizeTime(raw: string): string | null {
  const match = raw.trim().match(/^(\d{1,2}):(\d{1,2})$/);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

// "공고 업데이트 시간" — 최대 3개, 일부만 설정 가능. 드롭다운 3칸 방식(2026-09-05)이 칸이
// 많아 번거롭다는 지적(2026-09-07)으로 직접 입력(HH:MM 텍스트)으로 되돌리되, 형식·범위
// (00:00~23:59)는 입력창을 벗어날 때 검증한다. 저장만 하고 실제로 그 시각에 돌리는 실행
// 엔진(APScheduler)은 아직 없다(사용자 지시로 이번 범위 밖). 별도 "저장" 버튼은 없고
// 칸을 벗어나면(onBlur) 바로 저장되며, 결과는 토스트로 알린다.
function ScheduleTimesEditor({ sourceId, value }: { sourceId: number; value: string[] }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const mutation = useMutation({
    mutationFn: (times: string[]) => updateScheduleTimes(sourceId, times),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-sources"] });
      notify("success", "업데이트 시간을 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "업데이트 시간 저장에 실패했습니다.")),
  });

  const [drafts, setDrafts] = useState<string[]>(() => fillSlots(value));
  // 서버 값(저장 성공 포함)이 바뀌면 로컬 입력값도 맞춘다 — 단, 지금 타이핑 중인 칸까지
  // 덮어쓰면 안 되니 mutation이 도는 중엔 건드리지 않는다.
  useEffect(() => {
    if (!mutation.isPending) setDrafts(fillSlots(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  function commit(index: number, raw: string) {
    if (raw.trim() === "") {
      const updated = [...drafts];
      updated[index] = "";
      mutation.mutate(updated.filter(Boolean));
      return;
    }
    const normalized = normalizeTime(raw);
    if (normalized === null) return; // 형식이 틀리면 저장하지 않고 에러 표시만
    const updated = [...drafts];
    updated[index] = normalized;
    setDrafts(updated);
    mutation.mutate(updated.filter(Boolean));
  }

  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      {drafts.map((draft, i) => {
        const invalid = draft.trim() !== "" && normalizeTime(draft) === null;
        return (
          <TextField
            key={i}
            size="small"
            placeholder="HH:MM"
            value={draft}
            error={invalid}
            helperText={invalid ? "00:00~23:59" : undefined}
            disabled={mutation.isPending}
            sx={{ width: 92 }}
            onChange={(e) => {
              const next = [...drafts];
              next[i] = e.target.value;
              setDrafts(next);
            }}
            onBlur={(e) => commit(i, e.target.value)}
          />
        );
      })}
    </Stack>
  );
}

const LAST_RUN_STATUS_LABELS: Record<SourceRow["status"], string> = {
  ok: "성공", warn: "경고", fail: "실패", inactive: "비활성", no_run_yet: "기록 없음", running: "수집 중",
};
const LAST_RUN_STATUS_COLORS: Record<SourceRow["status"], "success" | "warning" | "error" | "info" | "default"> = {
  ok: "success", warn: "warning", fail: "error", inactive: "default", no_run_yet: "default", running: "info",
};

// 수동("지금 수집")·자동(스케줄러가 붙으면 그쪽) 어느 경로로 실행됐든 run_source()가 항상
// source_run에 기록을 남기므로(2026-09-07 요청) 이 값 하나로 양쪽을 다 보여줄 수 있다.
function LastRunCell({ status, lastRunAt }: { status: SourceRow["status"]; lastRunAt: string | null }) {
  return (
    <Stack spacing={0.25} alignItems="flex-end">
      <Chip
        size="small"
        label={LAST_RUN_STATUS_LABELS[status]}
        color={LAST_RUN_STATUS_COLORS[status]}
        variant={status === "ok" || status === "fail" || status === "running" ? "filled" : "outlined"}
      />
      {lastRunAt && (
        <Typography variant="caption" color="text.secondary">
          {new Date(lastRunAt).toLocaleString("ko-KR")}
        </Typography>
      )}
    </Stack>
  );
}

// 스케줄 시간을 서로 안 겹치게 잡으려면 실제 소요시간이 눈에 보여야 한다(2026-09-14 요청).
function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}초`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds === 0 ? `${minutes}분` : `${minutes}분 ${seconds}초`;
}

// "수집채널"과 "발주기관 현황"을 별개 메뉴로 분리(2026-09-05 요청) — 이전엔 SourcesPage
// 하나에 두 표가 같이 있어서 "채널 관리"와 "발주기관 조회"라는 서로 다른 목적이 섞여 있었다.
export function DataChannelsPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [noticeType, setNoticeType] = useState<"" | SourceRow["notice_type"]>("");

  // 서버가 실제로 수집 중인 소스가 있으면 짧은 주기로 자동 새로고침한다(2026-09-08) — 이
  // 탭이 시작한 게 아닌 수집(다른 탭·CLI·향후 스케줄러)도 "지금 수집" 버튼이 실시간으로
  // 비활성화되게 하기 위함. 아무도 안 돌리고 있으면(보통 상태) 폴링하지 않는다.
  const { data: sources, isLoading } = useQuery({
    queryKey: ["admin-sources"],
    queryFn: fetchSources,
    refetchInterval: (query) => (query.state.data?.some((row) => row.status === "running") ? 5000 : false),
  });

  const autoExtractMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => updateAutoExtract(id, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-sources"] });
      notify("success", "첨부문서 자동 분석 설정을 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "설정 저장에 실패했습니다.")),
  });

  const activeMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => updateActive(id, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-sources"] });
      notify("success", "공고 자동 수집 설정을 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "설정 저장에 실패했습니다.")),
  });

  const autoAnalyzeMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => updateAutoAnalyze(id, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-sources"] });
      notify("success", "AI 자동분석 설정을 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "설정 저장에 실패했습니다.")),
  });

  // 스케줄과 무관하게 관리자가 지금 즉시 1회 수집(2026-09-07 요청) — 실제 외부 API 호출이라
  // 몇십 초 걸리거나 실패할 수 있어, 성공·실패 모두 토스트로 명확히 알린다(AI분석 버튼이
  // 실패를 조용히 삼키던 것과 같은 실수를 반복하지 않기 위함).
  const collectNowMutation = useMutation({
    mutationFn: (sourceId: number) => collectNow(sourceId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["admin-sources"] });
      const parts = [
        `조회 ${result.fetched}건 · 신규 ${result.inserted}건 · 마감/기간외 제외 ${result.already_closed + result.out_of_window}건`,
      ];
      if (result.extraction_candidates > 0) parts.push(`첨부분석 ${result.auto_extracted}/${result.extraction_candidates}건`);
      if (result.analyze_candidates > 0) parts.push(`AI분석 ${result.auto_analyzed}/${result.analyze_candidates}건`);
      notify("success", `수집 완료 — ${parts.join(" · ")}`);
    },
    onError: (error) => notify("error", apiErrorMessage(error, "수집 중 오류가 발생했습니다.")),
  });

  const filteredSources = sources?.filter((row) => !noticeType || row.notice_type === noticeType);

  return (
    <Box>
      <Typography variant="h2" sx={{ mb: 0.5 }}>
        공고데이터 수집
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        나라장터·IRIS 등 실제로 공고를 가져오는 채널 목록입니다. "공고 자동 수집"을 끄면 이
        채널은 더 이상 수집되지 않습니다(수동 CLI 실행도 거부). "공고 업데이트 시간"은 설정값만
        저장합니다(실제 자동 실행은 아직 붙어있지 않음). "첨부문서 자동 분석"은 수집 시점에
        첨부파일 텍스트를 추출할지 여부(S8 A1, 판정 아님)만 결정합니다. "AI 자동분석"은 그
        추출이 성공했을 때 Haiku로 A2(요구사양 구조화, LLM 비용 발생)까지 자동으로 이어서
        실행할지 결정합니다 — 관리자가 여기서 켜둔 채널에만 적용됩니다.
      </Typography>

      <TextField
        select
        size="small"
        label="공고유형"
        value={noticeType}
        onChange={(e) => setNoticeType(e.target.value as "" | SourceRow["notice_type"])}
        sx={{ minWidth: 160, mb: 2 }}
      >
        <MenuItem value="">전체</MenuItem>
        {NOTICE_TYPES.map((t) => (
          <MenuItem key={t} value={t}>
            {t}
          </MenuItem>
        ))}
      </TextField>

      <Card sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>채널명</TableCell>
              <TableCell>공고유형</TableCell>
              <TableCell>공고 단계</TableCell>
              <TableCell>수집 방식</TableCell>
              <TableCell align="right">공고 자동 수집</TableCell>
              <TableCell>공고 업데이트 시간</TableCell>
              <TableCell align="right">첨부문서 자동 분석</TableCell>
              <TableCell align="right">AI 자동분석(Haiku)</TableCell>
              <TableCell align="right">지금 수집</TableCell>
              <TableCell align="right">최종 업데이트(수동/자동)</TableCell>
              <TableCell align="right">최근 소요시간</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!isLoading &&
              filteredSources?.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{row.name}</TableCell>
                  <TableCell>{row.notice_type}</TableCell>
                  <TableCell>{row.stage}</TableCell>
                  <TableCell>{row.adapter_label}</TableCell>
                  <TableCell align="right">
                    <Tooltip title={row.active ? "자동 수집 켜짐" : "자동 수집 꺼짐"}>
                      <Switch
                        size="small"
                        checked={row.active}
                        disabled={activeMutation.isPending}
                        onChange={(e) => activeMutation.mutate({ id: row.id, enabled: e.target.checked })}
                      />
                    </Tooltip>
                  </TableCell>
                  <TableCell>
                    <ScheduleTimesEditor sourceId={row.id} value={row.schedule_times} />
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title={row.auto_extract ? "자동 분석 켜짐" : "자동 분석 꺼짐"}>
                      <Switch
                        size="small"
                        checked={row.auto_extract}
                        disabled={autoExtractMutation.isPending}
                        onChange={(e) => autoExtractMutation.mutate({ id: row.id, enabled: e.target.checked })}
                      />
                    </Tooltip>
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title={row.auto_analyze ? "AI 자동분석 켜짐(비용 발생)" : "AI 자동분석 꺼짐"}>
                      <Switch
                        size="small"
                        checked={row.auto_analyze}
                        disabled={autoAnalyzeMutation.isPending}
                        onChange={(e) => autoAnalyzeMutation.mutate({ id: row.id, enabled: e.target.checked })}
                      />
                    </Tooltip>
                  </TableCell>
                  <TableCell align="right">
                    {(() => {
                      // 이 탭에서 방금 누른 것(로컬 mutation)뿐 아니라, 서버가 이미 진행 중이라고
                      // 알려주는 경우(다른 탭·새로고침·다른 관리자·향후 스케줄러)도 똑같이
                      // "수집 중"으로 표시하고 버튼을 막는다(2026-09-08 사용자 발견 — 로컬
                      // 로딩 상태만 보다가 페이지를 벗어났다 돌아오면 이미 끝난 것처럼 보였음).
                      const isLocallyPending = collectNowMutation.isPending && collectNowMutation.variables === row.id;
                      const isServerRunning = row.status === "running";
                      const isRunning = isLocallyPending || isServerRunning;
                      const tooltip = isServerRunning && !isLocallyPending
                        ? "이미 수집이 진행 중입니다(다른 탭·자동 실행 등)"
                        : row.active
                          ? "지금 즉시 1회 수집합니다"
                          : "자동 수집이 꺼진 채널입니다 — 켜야 수집할 수 있습니다";
                      return (
                        <Tooltip title={tooltip}>
                          <span>
                            <Button
                              size="small"
                              variant="outlined"
                              startIcon={isRunning ? <CircularProgress size={14} /> : <PlayArrowIcon />}
                              disabled={!row.active || isRunning}
                              onClick={() => collectNowMutation.mutate(row.id)}
                            >
                              {isRunning ? "수집 중…" : "지금 수집"}
                            </Button>
                          </span>
                        </Tooltip>
                      );
                    })()}
                  </TableCell>
                  <TableCell align="right">
                    <LastRunCell status={row.status} lastRunAt={row.last_run_at} />
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" color="text.secondary" className="tnum">
                      {formatDuration(row.last_duration_ms)}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </Card>
    </Box>
  );
}
