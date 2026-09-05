import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNewOutlined";
import { Box, Button, Card, Chip, Divider, IconButton, Link, MenuItem, Stack, TextField, Tooltip, Typography } from "@mui/material";

import type { AnalysisSummary, LlmModel } from "@/api/analysis";
import type { NoticeDetail } from "@/api/notices";

// opus는 여기 화면에서 선택지로 노출하지 않는다(비용이 커 CLI 수동 실행 전용으로 남김) —
// LlmModel 타입 자체엔 여전히 있어 Record 전체를 못 쓰고 필요한 2개만 배열로 나열.
const SELECTABLE_MODELS: { value: LlmModel; label: string }[] = [
  { value: "haiku", label: "Haiku (기본)" },
  { value: "sonnet", label: "Sonnet" },
];

// 달력 날짜 기준 D-day — 시각까지 포함한 순수 ms 차이로 계산하면 "오늘 마감"인데 아직 자정을
// 안 지났다는 이유로 D-1로 뜨는 버그가 있었다(2026-09-05, NoticeCard와 동일 로직 공유 필요성
// 있으나 지금은 각자 둠 — 중복 2곳뿐이라 공용 유틸로 뺄 정도는 아님).
function daysUntil(target: Date, now: Date): number {
  const startOfTarget = new Date(target.getFullYear(), target.getMonth(), target.getDate());
  const startOfNow = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((startOfTarget.getTime() - startOfNow.getTime()) / (1000 * 60 * 60 * 24));
}

function ddayInfo(closeDt: string | null): { label: string; urgent: boolean } | null {
  if (!closeDt) return null;
  const days = daysUntil(new Date(closeDt), new Date());
  if (days < 0) return null;
  return { label: days === 0 ? "D-Day" : `D-${days}`, urgent: days <= 3 };
}

// extra.ancmDe 등은 소스마다 원본 포맷이 제각각("2026-08-13" 처럼)이라 다른 날짜 필드(모두
// toLocaleDateString)와 표기가 달라 보였다(2026-09-05 지적) — 파싱 가능하면 같은 포맷으로 맞춘다.
function formatSourceDate(raw: string | null): string {
  if (!raw) return "—";
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? raw : parsed.toLocaleDateString("ko-KR");
}

export function NoticeTopSection({
  notice,
  summary,
  model,
  onModelChange,
  onRunAnalysis,
  analysisPending,
  analysisDone,
}: {
  notice: NoticeDetail;
  summary: AnalysisSummary | null | undefined;
  model: LlmModel;
  onModelChange: (model: LlmModel) => void;
  onRunAnalysis: () => void;
  analysisPending: boolean;
  analysisDone: boolean;
}) {
  const dday = ddayInfo(notice.close_dt);
  const isGovSupport = notice.notice_type === "정부지원";
  const announceDate = notice.extra?.ancmDe ? String(notice.extra.ancmDe) : null;
  const supervisingDept = notice.extra?.blngGovdSeNm ? String(notice.extra.blngGovdSeNm) : notice.channel_name;
  const taskType = summary?.task_type;
  const hasTaskType = taskType && (taskType.execution_system || taskType.development_form || taskType.call_type);
  const contact = summary?.contact;
  const hasContact = contact && (contact.department || contact.role || contact.phone || contact.email);

  return (
    <Card sx={{ p: 3 }}>
      <Stack spacing={2}>
        {/* 관심주제 — 사업명 위(2026-09-05 요청). 매칭 점수 표기는 뺀다(내부 키워드 가중치라
            업무 사용자에게 의미가 크지 않음 — 채팅에서 설명). */}
        {notice.scores.length > 0 && (
          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            {notice.scores.map((s) => (
              <Chip key={s.interest_topic_id} label={s.name} size="small" color="primary" variant="outlined" />
            ))}
          </Stack>
        )}

        {/* 가운데 세로줄로 좌/우 분할(2026-09-05 요청) — 내용에 비해 상단이 너무 넓어 보이던 문제 해소 */}
        <Stack direction="row" spacing={4} divider={<Divider orientation="vertical" flexItem />}>
          {/* 왼쪽: 공고 자체 정보 */}
          <Stack spacing={2} sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap alignItems="center">
              <Chip label={notice.notice_type} size="small" color="secondary" variant="outlined" />
              <Chip
                label={notice.notice_status_label}
                size="small"
                color={notice.bid_status === "in_progress" ? "success" : "default"}
                variant="outlined"
              />
              <Chip label={notice.work_type_label} size="small" variant="outlined" />
            </Stack>

            <Typography variant="h2">{notice.title}</Typography>

            {summary?.sub_business && <Field label="세부사업(내역사업)" value={summary.sub_business} />}

            <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap alignItems="flex-end">
              <Field label="총사업기간" value={summary?.project_period || "미분석"} />
              {/* 사업비는 참여 판단에서 가장 먼저 보는 값이라 크게 강조(2026-09-05 요청) */}
              <Field
                label="사업비"
                value={summary?.project_budget || (notice.est_price ? `${(notice.est_price / 100_000_000).toFixed(1)}억원` : "미공개")}
                large
              />
            </Stack>

            <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
              <Field label="공고일" value={formatSourceDate(announceDate)} />
              <Field label={isGovSupport ? "제안시작일" : "입찰시작일"} value={notice.open_dt ? new Date(notice.open_dt).toLocaleDateString("ko-KR") : "—"} />
              <Field
                label={isGovSupport ? "제안마감일" : "입찰마감일"}
                value={notice.close_dt ? new Date(notice.close_dt).toLocaleString("ko-KR") : "—"}
              />
            </Stack>
          </Stack>

          {/* 오른쪽: D-day·공고원문·AI분석(눈에 띄게) + 부가 정보 */}
          <Stack spacing={2} sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
              {dday && (
                <Chip
                  label={dday.label}
                  color={dday.urgent ? "error" : "default"}
                  variant={dday.urgent ? "filled" : "outlined"}
                  sx={{ fontWeight: 700, fontSize: "0.9rem", height: 32 }}
                />
              )}
              <Tooltip title="공고원문 보기">
                <IconButton
                  component={Link}
                  href={notice.url}
                  target="_blank"
                  rel="noreferrer"
                  color="primary"
                  sx={{ border: "1px solid", borderColor: "primary.main" }}
                >
                  <OpenInNewIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <TextField size="small" select value={model} onChange={(e) => onModelChange(e.target.value as LlmModel)} disabled={analysisDone} sx={{ minWidth: 120 }}>
                {SELECTABLE_MODELS.map((m) => (
                  <MenuItem key={m.value} value={m.value}>
                    {m.label}
                  </MenuItem>
                ))}
              </TextField>
              <Tooltip title={analysisDone ? "이미 분석이 완료됐습니다(중복 실행·LLM 비용 재발생 방지)" : "AI분석 실행"}>
                <span>
                  <Button
                    variant="contained"
                    startIcon={<AutoAwesomeOutlinedIcon />}
                    disabled={analysisPending || analysisDone}
                    onClick={onRunAnalysis}
                  >
                    {analysisPending ? "분석 중..." : analysisDone ? "분석 완료됨" : "AI분석"}
                  </Button>
                </span>
              </Tooltip>
            </Stack>

            {hasTaskType && (
              <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
                <Field label="추진체계" value={taskType!.execution_system || "—"} />
                <Field label="개발형태" value={taskType!.development_form || "—"} />
                <Field label="공모형태" value={taskType!.call_type || "—"} />
              </Stack>
            )}

            <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
              <Field label="발주기관" value={notice.org_name ?? "미상"} />
              <Field label="소관부처" value={supervisingDept ?? "—"} />
              <Field label="공고번호" value={notice.notice_no ?? "미부여"} />
            </Stack>

            {hasContact && (
              <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
                <Field label="담당자/직급" value={[contact!.department, contact!.role].filter(Boolean).join(" / ") || "—"} />
                <Field label="연락처" value={contact!.phone || "—"} />
                <Field label="이메일" value={contact!.email || "—"} />
              </Stack>
            )}
          </Stack>
        </Stack>
      </Stack>
    </Card>
  );
}

function Field({ label, value, large }: { label: string; value: string; large?: boolean }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant={large ? "h3" : "body2"} className="tnum" fontWeight={700} color={large ? "primary.main" : "text.primary"}>
        {value}
      </Typography>
    </Box>
  );
}
