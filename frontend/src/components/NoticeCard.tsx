import { Box, Card, Chip, Stack, Typography } from "@mui/material";
import { Link as RouterLink, useSearchParams } from "react-router-dom";

import { BID_STATUS_LABELS, type NoticeItem } from "@/api/notices";

// 사업목적 원문은 개조식 전문을 그대로 옮기다 보니 길어질 수 있어(2026-09-05) 카드에서는
// 300자로 자른다 — 전체는 상세 페이지("공고 상세분석" 섹션)에서 확인.
const MAX_PURPOSE_CHARS = 300;
function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

// 사업기간을 "N년 M개월"로만 보여준다(2026-09-05 요청) — AI 요약이 "43개월(당해 9개월),
// 과제별 상이"처럼 날짜범위·단서를 덧붙이는 경우가 많아, 괄호 앞부분(총량)만 취해 년/개월
// 숫자로 환산한다. 못 알아들으면(숫자 자체가 없으면) 원문을 그대로 보여준다(조용한 손실 방지).
function simplifyPeriod(raw: string): string {
  const prefix = raw.split("(")[0];
  const years = prefix.match(/(\d+)\s*년/);
  const months = prefix.match(/(\d+)\s*개월/);
  if (!years && !months) return raw;
  const totalMonths = (years ? parseInt(years[1], 10) * 12 : 0) + (months ? parseInt(months[1], 10) : 0);
  if (totalMonths === 0) return raw;
  const y = Math.floor(totalMonths / 12);
  const m = totalMonths % 12;
  return [y > 0 ? `${y}년` : "", m > 0 ? `${m}개월` : ""].filter(Boolean).join(" ");
}

function formatPrice(value: number | null): string {
  if (value === null) return "미공개";
  const eok = value / 100_000_000;
  return eok >= 1 ? `${eok.toFixed(1)}억원` : `${(value / 10_000).toFixed(0)}만원`;
}

// "공고일"(등록·게시 통지일, 참고용) — 소스마다 원본 필드명이 달라(IRIS는 ancmDe, 나라장터
// 발주계획현황서비스는 nticeDt) extra에서 둘 다 확인한다(NoticeTopSection.tsx와 동일 로직,
// 2026-09-07). open_dt(입찰 시작일)와는 다른 값 — 발주계획처럼 open_dt가 없는 단계에서도
// "언제 공고됐는지"를 보여줄 수 있다.
function formatAnnounceDate(extra: Record<string, string | number | null> | null): string {
  const raw = extra?.ancmDe ?? extra?.nticeDt;
  if (!raw) return "미상";
  const parsed = new Date(String(raw));
  return Number.isNaN(parsed.getTime()) ? String(raw) : parsed.toLocaleDateString("ko-KR");
}

// 달력 날짜 기준으로 며칠 남았는지 계산 — 시각까지 포함한 순수 ms 차이를 24시간으로 나누면
// "오늘 마감"인데 아직 몇 시간 안 지났다는 이유로 D-1로 뜨는 버그가 있었다(2026-09-05 발견,
// 마감일이 오늘인데 D-1로 표시됨). 두 시각 모두 자정 기준으로 깎아서 비교해야 "오늘=D-0"이
// 정확히 나온다.
function daysUntil(target: Date, now: Date): number {
  const startOfTarget = new Date(target.getFullYear(), target.getMonth(), target.getDate());
  const startOfNow = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((startOfTarget.getTime() - startOfNow.getTime()) / (1000 * 60 * 60 * 24));
}

function formatBidStatus(notice: NoticeItem): { label: string; urgent: boolean } {
  const urgent = notice.bid_status === "in_progress" && !!notice.close_dt && daysUntil(new Date(notice.close_dt), new Date()) <= 3;
  return { label: BID_STATUS_LABELS[notice.bid_status], urgent };
}

// D-day를 별도 칩으로 분리(2026-09-05 요청, 상세페이지와 동일한 강조 방식) — 마감이 임박하지
// 않아도 항상 채워진 색으로 표시해 다른 outlined 칩들 사이에서 눈에 띄게 한다.
function ddayInfo(closeDt: string | null): { label: string; urgent: boolean } | null {
  if (!closeDt) return null;
  const days = daysUntil(new Date(closeDt), new Date());
  if (days < 0) return null;
  return { label: days === 0 ? "D-Day" : `D-${days}`, urgent: days <= 3 };
}

interface Props {
  notice: NoticeItem;
  highlight?: string;
  // 가로형(list, 기본) — 한 줄에 하나, 정보를 옆으로 펼쳐 보여준다.
  // 세로형(grid) — 한 줄에 3개, 좁은 폭에 맞춰 위→아래로 쌓는다(2026-09-05 보기 스타일 추가).
  variant?: "list" | "grid";
}

// 분류검수 4버튼(카테고리 맞음/재분류/완전무관/심층분석)은 카드에서 제거했다(2026-09-05
// 사용자 지시) — 심층분석은 제목 클릭으로 이미 충분히 갈 수 있고, 나머지는 실사용 가치가
// 낮다고 판단. 유일하게 남긴 "관심주제 변경"은 상세페이지 AI분석 버튼 옆(TopicEditor)으로.
export function NoticeCard({ notice, highlight, variant = "list" }: Props) {
  const isGrid = variant === "grid";
  const bidStatus = formatBidStatus(notice);
  const [searchParams] = useSearchParams();

  const summary = notice.analysis_summary;
  // 사업비는 est_price(대부분 R&D 공고는 비어 있음)보다 A2 요약(summary.project_budget,
  // "150억원 이내(당해 19억원)"처럼 더 정확한 문구)이 있으면 그쪽을 우선한다(2026-09-05).
  const budgetLabel = summary?.project_budget || formatPrice(notice.est_price);
  const dday = ddayInfo(notice.close_dt);

  return (
    <Card sx={{ p: isGrid ? 2 : 2.5, height: isGrid ? "100%" : "auto", display: isGrid ? "flex" : "block", flexDirection: "column" }}>
      {/* 관심주제 + 공고유형/공고상태/업무구분을 한 줄로, 생명주기 상태 칩은 우측 최상단에
          고정(2026-09-05 요청) — "IRIS · 입찰공고"처럼 의미 없는 채널·stage 조합 대신 상세
          페이지와 같은 분류 체계(notice_classification.py)를 쓴다. */}
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1} sx={{ mb: 1 }}>
        <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ flex: 1, minWidth: 0 }}>
          {notice.scores.map((s) => (
            <Chip key={s.interest_topic_id} label={s.name} size="small" color="primary" variant="outlined" />
          ))}
          <Chip label={notice.notice_type} size="small" color="secondary" variant="outlined" />
          <Chip label={notice.notice_status_label} size="small" variant="outlined" />
          <Chip label={notice.work_type_label} size="small" variant="outlined" />
          {notice.assignee_name && <Chip label={`담당: ${notice.assignee_name}`} size="small" />}
        </Stack>
        <Chip
          label={bidStatus.label}
          size="small"
          color={bidStatus.urgent ? "error" : "default"}
          variant={bidStatus.urgent ? "filled" : "outlined"}
          sx={{ fontWeight: 700, flexShrink: 0 }}
        />
      </Stack>
      <Stack
        direction={isGrid ? "column" : "row"}
        justifyContent={isGrid ? "flex-start" : "space-between"}
        alignItems={isGrid ? "stretch" : "flex-start"}
        spacing={isGrid ? 1 : 2}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="h3"
            component={RouterLink}
            to={`/notices/${notice.id}?${searchParams.toString()}`}
            sx={{
              mb: 0.5,
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              color: "text.primary",
              "&:hover": { color: "primary.main" },
            }}
          >
            <HighlightedText text={notice.title} highlight={highlight} />
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {notice.org_name ?? "발주기관 미상"}
            {notice.region ? ` · ${notice.region}` : ""}
            {notice.notice_no ? ` · ${notice.notice_no}` : ""}
          </Typography>
          {/* 세부사업(내역사업) — 발주기관명과 같은 폰트 크기로(2026-09-05 요청, 이전엔 caption
              이라 너무 작아 보였음) */}
          {summary?.sub_business && (
            <Typography variant="body2" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
              세부사업: {summary.sub_business}
            </Typography>
          )}
          <Typography variant="body2" color="text.secondary" sx={{ display: "block", mt: 0.25 }} className="tnum">
            공고 {formatAnnounceDate(notice.extra)} · 게시{" "}
            {notice.open_dt ? new Date(notice.open_dt).toLocaleDateString("ko-KR") : "미상"} · 마감{" "}
            {notice.close_dt ? new Date(notice.close_dt).toLocaleDateString("ko-KR") : "미상"}
            {summary?.project_period ? ` · 총사업기간 ${simplifyPeriod(summary.project_period)}` : ""}
          </Typography>
        </Box>
        {/* 사업비·D-day는 참여 판단에 가장 먼저 눈에 들어와야 하는 값이라 다른 텍스트보다
            크고 진하게 둔다(2026-09-05 사용자 요청). */}
        <Stack
          direction={isGrid ? "row" : "column"}
          justifyContent={isGrid ? "space-between" : "flex-start"}
          alignItems={isGrid ? "center" : "flex-end"}
          spacing={0.5}
          sx={{ flexShrink: 0, maxWidth: isGrid ? "100%" : "45%", mt: isGrid ? 0.5 : 0 }}
        >
          {/* A2 요약의 project_budget은 가끔 한 문장 전체로 나올 만큼 길다(2026-09-13 실사용
              발견 — 카드 밖으로 텍스트가 넘치던 버그) — wordBreak+overflowWrap+maxWidth 셋을
              같이 둬야 어떤 길이든 이 블록 폭 안에서 줄바꿈된다. */}
          <Typography
            variant="h3"
            className="tnum"
            fontWeight={700}
            color="primary.main"
            sx={{ wordBreak: "keep-all", overflowWrap: "break-word", textAlign: isGrid ? "right" : "left" }}
          >
            {budgetLabel}
          </Typography>
          {dday && (
            <Chip
              label={dday.label}
              size="medium"
              color={dday.urgent ? "error" : "warning"}
              variant="filled"
              sx={{ fontWeight: 700 }}
            />
          )}
        </Stack>
      </Stack>

      {summary?.purpose && (
        // minHeight:0 — 이 Box가 세로형 카드의 flex(column) 컨테이너 안 자식이라, 기본값
        // (min-height:auto)이면 line-clamp를 넣어도 flex가 내용 높이만큼 억지로 늘려 카드
        // 밖으로 텍스트가 넘치는 문제가 있었다(2026-09-05 지적) — 0으로 줘야 line-clamp가 실제로 먹는다.
        <Box sx={{ mt: 1.5, p: 1, border: "1px solid", borderColor: "divider", borderRadius: 1, bgcolor: "action.hover", minHeight: 0, overflow: "hidden" }}>
          <Typography
            variant="body2"
            sx={{
              fontWeight: 600,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              display: "-webkit-box",
              WebkitLineClamp: 6,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            과제목표 — {truncate(summary.purpose, MAX_PURPOSE_CHARS)}
          </Typography>
        </Box>
      )}


    </Card>
  );
}

function HighlightedText({ text, highlight }: { text: string; highlight?: string }) {
  if (!highlight) return <>{text}</>;
  const index = text.toLowerCase().indexOf(highlight.toLowerCase());
  if (index === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <Box component="mark" sx={{ bgcolor: "primary.lighter", color: "primary.darker", px: 0.25 }}>
        {text.slice(index, index + highlight.length)}
      </Box>
      {text.slice(index + highlight.length)}
    </>
  );
}
