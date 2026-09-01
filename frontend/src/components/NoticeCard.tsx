import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import DriveFileMoveOutlinedIcon from "@mui/icons-material/DriveFileMoveOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import BlockOutlinedIcon from "@mui/icons-material/BlockOutlined";
import { Box, Button, Card, Chip, Divider, Stack, Tooltip, Typography } from "@mui/material";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link as RouterLink, useSearchParams } from "react-router-dom";

import { submitClassification, type ClassificationAction } from "@/api/classification";
import type { FilterOptions, NoticeItem } from "@/api/notices";
import { ClassificationDialog } from "@/components/ClassificationDialog";

function formatPrice(value: number | null): string {
  if (value === null) return "미공개";
  const eok = value / 100_000_000;
  return eok >= 1 ? `${eok.toFixed(1)}억원` : `${(value / 10_000).toFixed(0)}만원`;
}

function formatDday(closeDt: string | null): { label: string; urgent: boolean } | null {
  if (!closeDt) return null;
  const diffMs = new Date(closeDt).getTime() - Date.now();
  const days = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  if (days < 0) return { label: "마감", urgent: false };
  return { label: days === 0 ? "D-Day" : `D-${days}`, urgent: days <= 3 };
}

interface Props {
  notice: NoticeItem;
  highlight?: string;
  topics: FilterOptions["topics"];
  classifiedAs: ClassificationAction | null;
  onClassified: (noticeId: number, action: ClassificationAction) => void;
}

// U5 인수조건: "카드만 갱신(목록 리로드 없음)" — 분류검수 액션은 목록을 다시 안 부르고
// 이 카드의 로컬 상태(classifiedAs, 부모가 들고 있음)만 바꾼다.
export function NoticeCard({ notice, highlight, topics, classifiedAs, onClassified }: Props) {
  const dday = formatDday(notice.close_dt);
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

  return (
    <Card sx={{ p: 2.5, opacity: classifiedAs ? 0.7 : 1 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
        <Box sx={{ minWidth: 0 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
            <Chip label={notice.stage} size="small" color="secondary" variant="outlined" />
            {notice.assignee_name && <Chip label={`담당: ${notice.assignee_name}`} size="small" />}
            {classifiedAs && <Chip label={CLASSIFIED_LABEL[classifiedAs]} size="small" color="success" />}
          </Stack>
          <Typography
            variant="h3"
            component={RouterLink}
            to={`/notices/${notice.id}?${searchParams.toString()}`}
            sx={{ mb: 0.5, display: "block", color: "text.primary", "&:hover": { color: "primary.main" } }}
          >
            <HighlightedText text={notice.title} highlight={highlight} />
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {notice.org_name ?? "발주기관 미상"}
            {notice.region ? ` · ${notice.region}` : ""}
          </Typography>
        </Box>
        <Stack alignItems="flex-end" spacing={0.5} sx={{ flexShrink: 0 }}>
          <Typography variant="body2" className="tnum" fontWeight={600}>
            {formatPrice(notice.est_price)}
          </Typography>
          {dday && (
            <Chip
              label={dday.label}
              size="small"
              color={dday.urgent ? "error" : "default"}
              variant={dday.urgent ? "filled" : "outlined"}
            />
          )}
        </Stack>
      </Stack>

      <Divider sx={{ my: 1.5 }} />

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
        <Tooltip title="심층 분석은 다음 작업 단위(U9)에서 제공됩니다">
          <span style={{ marginLeft: "auto" }}>
            <Button size="small" variant="outlined" startIcon={<AutoAwesomeOutlinedIcon fontSize="small" />} disabled>
              심층 분석
            </Button>
          </span>
        </Tooltip>
      </Stack>

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
