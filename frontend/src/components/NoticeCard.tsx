import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import DriveFileMoveOutlinedIcon from "@mui/icons-material/DriveFileMoveOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import BlockOutlinedIcon from "@mui/icons-material/BlockOutlined";
import { Box, Button, Card, Chip, Divider, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link as RouterLink, useSearchParams } from "react-router-dom";

import { submitClassification, type ClassificationAction } from "@/api/classification";
import {
  BID_STATUS_LABELS,
  EXTRA_FIELD_LABELS,
  formatExtraValue,
  type FilterOptions,
  type NoticeItem,
} from "@/api/notices";
import { ClassificationDialog } from "@/components/ClassificationDialog";

function formatPrice(value: number | null): string {
  if (value === null) return "미공개";
  const eok = value / 100_000_000;
  return eok >= 1 ? `${eok.toFixed(1)}억원` : `${(value / 10_000).toFixed(0)}만원`;
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

// 공고 생명주기 상태(2026-09-03, 입찰미정→입찰예정→입찰접수→입찰마감) 칩 — "입찰접수"이면서
// 마감일이 있으면 D-day까지 같이 보여준다(예: "입찰접수 · D-3"), 그 외엔 상태 라벨만.
function formatBidStatus(notice: NoticeItem): { label: string; urgent: boolean } {
  if (notice.bid_status === "in_progress" && notice.close_dt) {
    const days = daysUntil(new Date(notice.close_dt), new Date());
    const dday = days === 0 ? "D-Day" : `D-${days}`;
    return { label: `입찰접수 · ${dday}`, urgent: days <= 3 };
  }
  return { label: BID_STATUS_LABELS[notice.bid_status], urgent: false };
}

interface Props {
  notice: NoticeItem;
  highlight?: string;
  topics: FilterOptions["topics"];
  classifiedAs: ClassificationAction | null;
  onClassified: (noticeId: number, action: ClassificationAction) => void;
  // 가로형(list, 기본) — 한 줄에 하나, 정보를 옆으로 펼쳐 보여준다.
  // 세로형(grid) — 한 줄에 3개, 좁은 폭에 맞춰 위→아래로 쌓는다(2026-09-05 보기 스타일 추가).
  variant?: "list" | "grid";
}

// U5 인수조건: "카드만 갱신(목록 리로드 없음)" — 분류검수 액션은 목록을 다시 안 부르고
// 이 카드의 로컬 상태(classifiedAs, 부모가 들고 있음)만 바꾼다.
export function NoticeCard({ notice, highlight, topics, classifiedAs, onClassified, variant = "list" }: Props) {
  const isGrid = variant === "grid";
  const bidStatus = formatBidStatus(notice);
  const [searchParams] = useSearchParams();
  const [dialogAction, setDialogAction] = useState<Extract<ClassificationAction, "recategorize" | "irrelevant"> | null>(
    null,
  );

  const mutation = useMutation({
    mutationFn: (payload: { action: ClassificationAction; categories?: number[]; reason?: string }) =>
      submitClassification(notice.id, payload),
    onSuccess: (_, variables) => {
      onClassified(notice.id, variables.action);
      setDialogAction(null);
    },
  });

  const summary = notice.analysis_summary;
  // 사업비는 est_price(대부분 R&D 공고는 비어 있음)보다 A2 요약(summary.project_budget,
  // "150억원 이내(당해 19억원)"처럼 더 정확한 문구)이 있으면 그쪽을 우선한다(2026-09-05).
  const budgetLabel = summary?.project_budget || formatPrice(notice.est_price);

  return (
    <Card sx={{ p: isGrid ? 2 : 2.5, opacity: classifiedAs ? 0.7 : 1, height: isGrid ? "100%" : "auto", display: isGrid ? "flex" : "block", flexDirection: "column" }}>
      <Stack
        direction={isGrid ? "column" : "row"}
        justifyContent={isGrid ? "flex-start" : "space-between"}
        alignItems={isGrid ? "stretch" : "flex-start"}
        spacing={isGrid ? 1 : 2}
      >
        <Box sx={{ minWidth: 0 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }} flexWrap="wrap" useFlexGap>
            <Chip label={notice.stage} size="small" color="secondary" variant="outlined" />
            {notice.biz_type && <Chip label={notice.biz_type} size="small" variant="outlined" />}
            {!isGrid && notice.work_type && <Chip label={notice.work_type} size="small" variant="outlined" />}
            {!isGrid && notice.assignee_name && <Chip label={`담당: ${notice.assignee_name}`} size="small" />}
            {classifiedAs && <Chip label={CLASSIFIED_LABEL[classifiedAs]} size="small" color="success" />}
          </Stack>
          <Typography
            variant="h3"
            component={RouterLink}
            to={`/notices/${notice.id}?${searchParams.toString()}`}
            sx={{
              mb: 0.5,
              display: isGrid ? "-webkit-box" : "block",
              WebkitLineClamp: isGrid ? 2 : undefined,
              WebkitBoxOrient: isGrid ? "vertical" : undefined,
              overflow: isGrid ? "hidden" : undefined,
              color: "text.primary",
              "&:hover": { color: "primary.main" },
            }}
          >
            <HighlightedText text={notice.title} highlight={highlight} />
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {notice.org_name ?? "발주기관 미상"}
            {notice.region ? ` · ${notice.region}` : ""}
            {!isGrid && notice.notice_no ? ` · 공고번호 ${notice.notice_no}` : ""}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }} className="tnum">
            게시 {notice.open_dt ? new Date(notice.open_dt).toLocaleDateString("ko-KR") : "미상"} · 마감{" "}
            {notice.close_dt ? new Date(notice.close_dt).toLocaleDateString("ko-KR") : "미상"}
            {!isGrid && summary?.project_period ? ` · 총사업기간 ${summary.project_period}` : ""}
          </Typography>
        </Box>
        {/* 사업비·D-day는 참여 판단에 가장 먼저 눈에 들어와야 하는 값이라 다른 텍스트보다
            크고 진하게 둔다(2026-09-05 사용자 요청). */}
        <Stack
          direction={isGrid ? "row" : "column"}
          justifyContent={isGrid ? "space-between" : "flex-start"}
          alignItems={isGrid ? "center" : "flex-end"}
          spacing={0.5}
          sx={{ flexShrink: 0, mt: isGrid ? 0.5 : 0 }}
        >
          <Typography variant="h3" className="tnum" fontWeight={700} color="primary.main" sx={{ whiteSpace: "nowrap" }}>
            {budgetLabel}
          </Typography>
          <Chip
            label={bidStatus.label}
            size="medium"
            color={bidStatus.urgent ? "error" : "default"}
            variant={bidStatus.urgent ? "filled" : "outlined"}
            sx={{ fontWeight: 700 }}
          />
        </Stack>
      </Stack>

      {summary && (summary.purpose || summary.content_narrative) && (
        <Box sx={{ mt: 1.5 }}>
          {summary.purpose && (
            <Typography
              variant="body2"
              sx={
                isGrid
                  ? { fontWeight: 600, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }
                  : { fontWeight: 600 }
              }
            >
              과제목표 — {summary.purpose}
            </Typography>
          )}
          {summary.content_narrative && (
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{
                mt: 0.25,
                display: "-webkit-box",
                WebkitLineClamp: isGrid ? 2 : 3,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}
            >
              과제내용 — {summary.content_narrative}
            </Typography>
          )}
        </Box>
      )}

      {!isGrid && notice.extra && Object.keys(notice.extra).length > 0 && (
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mt: 1.5 }}>
          {Object.entries(notice.extra).map(([key, value]) => {
            const formatted = formatExtraValue(key, value);
            // 카드는 공간이 좁아 긴 요약 텍스트(사업내용 등)는 잘라서 보여준다 — 전체는 상세
            // 페이지에서 확인.
            const shown = formatted.length > 40 ? `${formatted.slice(0, 40)}…` : formatted;
            return (
              <Tooltip key={key} title={formatted.length > 40 ? formatted : ""} disableHoverListener={formatted.length <= 40}>
                <Chip size="small" variant="outlined" label={`${EXTRA_FIELD_LABELS[key] ?? key}: ${shown}`} />
              </Tooltip>
            );
          })}
        </Stack>
      )}

      <Box sx={{ flexGrow: isGrid ? 1 : undefined }} />
      <Divider sx={{ my: 1.5 }} />

      {isGrid ? (
        // 좁은 폭에서는 라벨 텍스트 대신 아이콘 버튼으로 — 4개 버튼이 한 줄에 다 들어가야 함.
        <Stack direction="row" spacing={0.5} justifyContent="space-between">
          <Tooltip title="카테고리 맞음">
            <span>
              <IconButton size="small" disabled={mutation.isPending} onClick={() => mutation.mutate({ action: "confirm" })}>
                <CheckCircleOutlineIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="카테고리 재분류">
            <span>
              <IconButton size="small" disabled={mutation.isPending} onClick={() => setDialogAction("recategorize")}>
                <DriveFileMoveOutlinedIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="완전 무관">
            <span>
              <IconButton size="small" color="error" disabled={mutation.isPending} onClick={() => setDialogAction("irrelevant")}>
                <BlockOutlinedIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="심층 분석">
            <IconButton size="small" color="primary" component={RouterLink} to={`/notices/${notice.id}?${searchParams.toString()}`}>
              <AutoAwesomeOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      ) : (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button
            size="small"
            startIcon={<CheckCircleOutlineIcon fontSize="small" />}
            disabled={mutation.isPending}
            onClick={() => mutation.mutate({ action: "confirm" })}
          >
            카테고리 맞음
          </Button>
          <Button
            size="small"
            startIcon={<DriveFileMoveOutlinedIcon fontSize="small" />}
            disabled={mutation.isPending}
            onClick={() => setDialogAction("recategorize")}
          >
            카테고리 재분류
          </Button>
          <Button
            size="small"
            color="error"
            startIcon={<BlockOutlinedIcon fontSize="small" />}
            disabled={mutation.isPending}
            onClick={() => setDialogAction("irrelevant")}
          >
            완전 무관
          </Button>
          <Button
            size="small"
            variant="outlined"
            startIcon={<AutoAwesomeOutlinedIcon fontSize="small" />}
            component={RouterLink}
            to={`/notices/${notice.id}?${searchParams.toString()}`}
            sx={{ ml: "auto" }}
          >
            심층 분석
          </Button>
        </Stack>
      )}

      {dialogAction && (
        <ClassificationDialog
          open
          action={dialogAction}
          topics={topics}
          submitting={mutation.isPending}
          onClose={() => setDialogAction(null)}
          onSubmit={(payload) => mutation.mutate({ action: dialogAction, ...payload })}
        />
      )}
    </Card>
  );
}

const CLASSIFIED_LABEL: Record<ClassificationAction, string> = {
  confirm: "확인됨",
  recategorize: "재분류됨",
  irrelevant: "무관 처리됨",
};

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
