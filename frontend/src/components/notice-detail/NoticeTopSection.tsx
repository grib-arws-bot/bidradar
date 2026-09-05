import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import NotificationsOutlinedIcon from "@mui/icons-material/NotificationsOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNewOutlined";
import { Box, Button, Card, Chip, Link, Stack, Typography } from "@mui/material";

import type { AnalysisSummary } from "@/api/analysis";
import type { NoticeDetail } from "@/api/notices";

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

export function NoticeTopSection({
  notice,
  summary,
  onFollow,
  followPending,
}: {
  notice: NoticeDetail;
  summary: AnalysisSummary | null | undefined;
  onFollow: () => void;
  followPending: boolean;
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
      <Stack spacing={2.5}>
        {/* 1. 공고유형·공고상태·업무구분 */}
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap alignItems="center">
          <Chip label={notice.notice_type} size="small" color="secondary" variant="outlined" />
          <Chip
            label={notice.notice_status_label}
            size="small"
            color={notice.bid_status === "in_progress" ? "success" : "default"}
            variant="outlined"
          />
          <Chip label={notice.work_type_label} size="small" variant="outlined" />
          {dday && <Chip label={dday.label} size="medium" color={dday.urgent ? "error" : "default"} variant={dday.urgent ? "filled" : "outlined"} sx={{ fontWeight: 700 }} />}
        </Stack>

        {/* 2. 사업명(과제명) */}
        <Typography variant="h2">{notice.title}</Typography>

        {/* 3. 세부사업(내역사업) */}
        {summary?.sub_business && <Field label="세부사업(내역사업)" value={summary.sub_business} />}

        {/* 4. 과제유형: 추진체계·개발형태·공모형태 */}
        {hasTaskType && (
          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
            <Field label="추진체계" value={taskType!.execution_system || "—"} />
            <Field label="개발형태" value={taskType!.development_form || "—"} />
            <Field label="공모형태" value={taskType!.call_type || "—"} />
          </Stack>
        )}

        {/* 5. 발주기관·공고기관(소관부처)·공고번호·총사업기간·사업비·(공고보기) */}
        <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap alignItems="flex-end">
          <Field label="발주기관" value={notice.org_name ?? "미상"} />
          <Field label="공고기관(소관부처)" value={supervisingDept ?? "—"} />
          <Field label="공고번호" value={notice.notice_no ?? "미부여"} />
          <Field label="총사업기간" value={summary?.project_period || "미분석"} />
          {/* 사업비는 참여 판단에서 가장 먼저 보는 값이라 크게 강조(2026-09-05 요청) */}
          <Field
            label="사업비"
            value={summary?.project_budget || (notice.est_price ? `${(notice.est_price / 100_000_000).toFixed(1)}억원` : "미공개")}
            large
          />
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              공고보기
            </Typography>
            <Button
              size="small"
              variant="outlined"
              startIcon={<OpenInNewIcon fontSize="small" />}
              component={Link}
              href={notice.url}
              target="_blank"
              rel="noreferrer"
            >
              원문 링크
            </Button>
          </Box>
        </Stack>

        {/* 6. 공고일·입찰(제안)시작일·입찰(제안)마감일·D-day */}
        <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap alignItems="flex-end">
          <Field label="공고일" value={announceDate ?? "—"} />
          <Field label={isGovSupport ? "제안시작일" : "입찰시작일"} value={notice.open_dt ? new Date(notice.open_dt).toLocaleDateString("ko-KR") : "—"} />
          <Field
            label={isGovSupport ? "제안마감일" : "입찰마감일"}
            value={notice.close_dt ? new Date(notice.close_dt).toLocaleString("ko-KR") : "—"}
          />
          {dday && <Field label="D-day" value={dday.label} large />}
        </Stack>

        {/* 7. 문의처: 이름(미제공)·소속·직급·연락처·이메일 */}
        {hasContact && (
          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
            <Field label="소속" value={contact!.department || "—"} />
            <Field label="직급" value={contact!.role || "—"} />
            <Field label="연락처" value={contact!.phone || "—"} />
            <Field label="이메일" value={contact!.email || "—"} />
          </Stack>
        )}

        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Button
            variant={notice.org_followed ? "contained" : "outlined"}
            size="small"
            startIcon={notice.org_followed ? <NotificationsActiveIcon /> : <NotificationsOutlinedIcon />}
            disabled={followPending || notice.org_followed}
            onClick={onFollow}
          >
            {notice.org_followed ? "팔로우 중" : "이 기관 팔로우"}
          </Button>
          {notice.scores.map((s) => (
            <Chip key={s.interest_topic_id} label={`${s.name} (+${s.l2_score})`} size="small" />
          ))}
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
