import { useState } from "react";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNewOutlined";
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
  Divider,
  FormControlLabel,
  Link,
  Radio,
  RadioGroup,
  Stack,
  Typography,
} from "@mui/material";

import type { AnalysisSummary, LlmModel } from "@/api/analysis";
import type { FilterOptions, NoticeDetail } from "@/api/notices";
import { TopicEditor } from "@/components/notice-detail/TopicEditor";
import { isAttachmentDownloadUrl } from "@/utils/noticeLinks";

const SELECTABLE_MODELS: { value: LlmModel; label: string }[] = [
  { value: "haiku", label: "Haiku (기본, 저렴)" },
  { value: "sonnet", label: "Sonnet (고품질, 비용↑)" },
];

// 달력 날짜 기준 D-day — 시각까지 포함한 순수 ms 차이로 계산하면 "오늘 마감"인데 아직 자정을
// 안 지났다는 이유로 D-1로 뜨는 버그가 있었다(2026-09-05, NoticeCard와 동일 로직 공유 필요성
// 있으나 지금은 각자 둠 — 중복 2곳뿐이라 공용 유틸로 뺄 정도는 아님).
function daysUntil(target: Date, now: Date): number {
  const startOfTarget = new Date(target.getFullYear(), target.getMonth(), target.getDate());
  const startOfNow = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((startOfTarget.getTime() - startOfNow.getTime()) / (1000 * 60 * 60 * 24));
}

// 마감이 임박하지 않아도(예: D-6) 다른 outlined 칩들 사이에 묻혀 눈에 안 띈다는 지적(2026-09-05)
// — D-day는 항상 채워진 색으로 강조하고, 임박(3일 이내)할 때만 색을 error로 바꾼다.
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
  onRunAnalysis,
  analysisPending,
  analysisDone,
  analysisError,
  allTopics,
}: {
  notice: NoticeDetail;
  summary: AnalysisSummary | null | undefined;
  onRunAnalysis: (model: LlmModel) => void;
  analysisPending: boolean;
  analysisDone: boolean;
  analysisError?: string | null;
  allTopics: FilterOptions["topics"];
}) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogModel, setDialogModel] = useState<LlmModel>("haiku");
  const dday = ddayInfo(notice.close_dt);
  const isGovSupport = notice.notice_type === "정부지원";
  // "공고일" 참고용 등록일 — 소스마다 원본 필드명이 다르다(IRIS는 ancmDe, 나라장터
  // 발주계획현황서비스는 nticeDt). 둘 다 "입찰 시작일이 아닌 단순 등록일"이라 open_dt로는
  // 안 쓰고 extra에만 참고용으로 남겨뒀는데(2026-09-05 결정), 발주계획 공고는 nticeDt를
  // 안 봐서 "공고일"이 항상 비어 보이던 문제(2026-09-07 발견) — 두 필드명 다 확인한다.
  const announceDate = notice.extra?.ancmDe ?? notice.extra?.nticeDt;
  const announceDateStr = announceDate ? String(announceDate) : null;
  const supervisingDept = notice.extra?.blngGovdSeNm ? String(notice.extra.blngGovdSeNm) : notice.channel_name;
  const taskType = summary?.task_type;
  const hasTaskType = taskType && (taskType.execution_system || taskType.development_form || taskType.call_type);
  const contact = summary?.contact;
  const hasContact = contact && (contact.department || contact.role || contact.phone || contact.email);

  function confirmRunAnalysis() {
    setDialogOpen(false);
    onRunAnalysis(dialogModel);
  }

  return (
    <Card sx={{ p: 3 }}>
      <Stack spacing={2}>
        {/* 공고유형/상태/업무구분 한 줄로(2026-09-05 요청) — 관심주제(TopicEditor)는 왼쪽
            컬럼의 공고일 아래로 옮겼다(2026-09-07 재배치, 카드의 분류검수 4버튼을 없애면서
            유일하게 남긴 기능). */}
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

        {/* 가운데 세로줄로 좌/우 분할(2026-09-05 요청) — 내용에 비해 상단이 너무 넓어 보이던 문제 해소 */}
        <Stack direction="row" spacing={4} divider={<Divider orientation="vertical" flexItem />}>
          {/* 왼쪽: 공고 자체 정보 */}
          <Stack spacing={2} sx={{ flex: 1, minWidth: 0 }}>

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
              <Field label="공고일" value={formatSourceDate(announceDateStr)} />
              <Field label={isGovSupport ? "제안시작일" : "입찰시작일"} value={notice.open_dt ? new Date(notice.open_dt).toLocaleDateString("ko-KR") : "—"} />
              {/* 마감일은 참여 판단 마지노선이라 사업비와 같은 강조(주황·큰 폰트)로(2026-09-05 요청) */}
              <Field
                label={isGovSupport ? "제안마감일" : "입찰마감일"}
                value={notice.close_dt ? new Date(notice.close_dt).toLocaleString("ko-KR") : "—"}
                large
              />
            </Stack>

            {/* 관심주제를 공고일 아래로(2026-09-07 요청) — 예전엔 AI분석 버튼 옆에 있었음 */}
            <TopicEditor noticeId={notice.id} scores={notice.scores} allTopics={allTopics} />
          </Stack>

          {/* 오른쪽: D-day·공고원문·AI분석·관심주제를 한 덩어리로(2026-09-05 "일관된 UI로"
              요청) — 전부 한 줄(래핑 허용)에 같은 높이(size="medium")로 맞춘다. */}
          <Stack spacing={1.5} sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
              {dday && (
                <Chip
                  label={dday.label}
                  size="medium"
                  color={dday.urgent ? "error" : "warning"}
                  variant="filled"
                  sx={{ fontWeight: 700, fontSize: "0.9rem" }}
                />
              )}
              <Button
                size="medium"
                variant="outlined"
                startIcon={
                  isAttachmentDownloadUrl(notice.url) ? (
                    <DownloadOutlinedIcon fontSize="small" />
                  ) : (
                    <OpenInNewIcon fontSize="small" />
                  )
                }
                component={Link}
                href={notice.url}
                target="_blank"
                rel="noreferrer"
              >
                {isAttachmentDownloadUrl(notice.url) ? "규격서 파일 다운로드" : "공고원문보기"}
              </Button>
              <Button
                size="medium"
                variant="contained"
                startIcon={<AutoAwesomeOutlinedIcon />}
                disabled={analysisPending}
                onClick={() => setDialogOpen(true)}
              >
                {analysisPending ? "분석 중..." : analysisDone ? "재분석" : "AI분석"}
              </Button>
            </Stack>

            {/* 2026-09-06 — 추출(A1) 실패는 예외 없이 정상 응답(status:"failed")으로 오기 때문에
                예전엔 버튼을 눌러도 아무 반응이 없는 것처럼 보였다("AI분석이 다시 실행되지
                않는 것 같다" 문의로 발견). 실패 사유를 그대로 보여준다. */}
            {analysisError && <Alert severity="error">AI분석 실패: {analysisError}</Alert>}

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

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{analysisDone ? "재분석 실행" : "AI분석 실행"}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            LLM 호출 비용이 발생합니다{analysisDone ? " — 재분석하면 이 페이지에 보이는 내용이 새 결과로 전부 바뀝니다(이전 결과를 다시 볼 수 있는 화면은 없습니다)" : ""}.
          </Alert>
          <RadioGroup value={dialogModel} onChange={(e) => setDialogModel(e.target.value as LlmModel)}>
            {SELECTABLE_MODELS.map((m) => (
              <FormControlLabel key={m.value} value={m.value} control={<Radio />} label={m.label} />
            ))}
          </RadioGroup>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>취소</Button>
          <Button variant="contained" onClick={confirmRunAnalysis}>
            확인
          </Button>
        </DialogActions>
      </Dialog>
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
