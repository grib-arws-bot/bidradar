import ArrowBackIcon from "@mui/icons-material/ArrowBackOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNewOutlined";
import { Box, Button, Card, Chip, CircularProgress, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { Link as RouterLink, useParams } from "react-router-dom";

import { BID_STATUS_LABELS } from "@/api/notices";
import { fetchPublicNotice } from "@/api/reports";
import Logo from "@/components/Logo";
import { isAttachmentDownloadUrl } from "@/utils/noticeLinks";

function formatPrice(value: number | null): string {
  if (value === null) return "미공개";
  const eok = value / 100_000_000;
  return eok >= 1 ? `${eok.toFixed(1)}억원` : `${(value / 10_000).toFixed(0)}만원`;
}

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

function Field({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={600}>
        {value}
      </Typography>
    </Box>
  );
}

// 공개(비로그인) 공고 상세 — 리포트에서 공고를 클릭하면 온다. 내부 관리자 화면(NoticeTopSection)
// 과 같은 정보 구성이되, 담당자 배정·자사 제품 충족판정 등 내부 전용 항목은 뺀 버전
// (app/services/notice_strategy.py get_public_notice_summary가 이미 걸러서 준다).
export function PublicNoticeDetailPage() {
  const { token, noticeId } = useParams<{ token: string; noticeId: string }>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["public-notice", token, noticeId],
    queryFn: () => fetchPublicNotice(token!, Number(noticeId)),
    retry: false,
  });

  if (isLoading) {
    return (
      <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (isError || !data) {
    return (
      <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <Typography>공고를 찾을 수 없습니다.</Typography>
      </Box>
    );
  }

  const dday = ddayInfo(data.close_dt);
  const summary = data.ai_summary as
    | { project_period?: string; project_budget?: string; purpose?: string; sub_business?: string }
    | null;

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default", py: { xs: 3, md: 6 } }}>
      <Stack spacing={3} sx={{ maxWidth: 720, mx: "auto", px: 2 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Logo size={34} />
        </Stack>

        <Button component={RouterLink} to={`/r/${token}`} startIcon={<ArrowBackIcon />} sx={{ alignSelf: "flex-start" }}>
          리포트로 돌아가기
        </Button>

        <Card sx={{ p: 3 }}>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
            <Chip label={data.notice_type} size="small" color="secondary" variant="outlined" />
            <Chip label={data.notice_status_label} size="small" variant="outlined" />
            <Chip label={data.work_type_label} size="small" variant="outlined" />
            <Chip
              label={BID_STATUS_LABELS[data.bid_status]}
              size="small"
              color={data.bid_status === "in_progress" ? "error" : "default"}
              variant={data.bid_status === "in_progress" ? "filled" : "outlined"}
              sx={{ fontWeight: 700 }}
            />
          </Stack>

          <Typography variant="h2" sx={{ mb: 1 }}>
            {data.title}
          </Typography>

          {summary?.sub_business && <Field label="세부사업(내역사업)" value={summary.sub_business} />}

          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap sx={{ mt: 2 }}>
            <Field label="총사업기간" value={summary?.project_period || "미분석"} />
            <Field label="사업비" value={summary?.project_budget || formatPrice(data.est_price)} />
          </Stack>

          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap sx={{ mt: 2 }}>
            <Field label="발주기관" value={data.org_name ?? "미상"} />
            <Field label="지역" value={data.region ?? "—"} />
            <Field label="공고번호" value={data.notice_no ?? "미부여"} />
          </Stack>

          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap alignItems="center" sx={{ mt: 2 }}>
            <Field
              label="게시일"
              value={data.open_dt ? new Date(data.open_dt).toLocaleDateString("ko-KR") : "—"}
            />
            <Field
              label="마감일"
              value={data.close_dt ? new Date(data.close_dt).toLocaleString("ko-KR") : "—"}
            />
            {dday && (
              <Chip label={dday.label} size="medium" color={dday.urgent ? "error" : "warning"} variant="filled" sx={{ fontWeight: 700 }} />
            )}
          </Stack>

          {summary?.purpose && (
            <Box sx={{ mt: 2, p: 1.5, borderRadius: 1, bgcolor: "action.hover" }}>
              <Typography variant="body2" fontWeight={600} sx={{ whiteSpace: "pre-wrap" }}>
                과제목표 — {summary.purpose}
              </Typography>
            </Box>
          )}

          <Stack direction="row" spacing={1.5} sx={{ mt: 3 }}>
            <Button
              variant="outlined"
              startIcon={isAttachmentDownloadUrl(data.url) ? <DownloadOutlinedIcon /> : <OpenInNewIcon />}
              component="a"
              href={data.url}
              target="_blank"
              rel="noreferrer"
            >
              {isAttachmentDownloadUrl(data.url) ? "규격서 파일 다운로드" : "공고원문보기"}
            </Button>
            <Button
              variant="contained"
              startIcon={<AutoAwesomeOutlinedIcon />}
              component={RouterLink}
              to={`/r/${token}/notices/${noticeId}/strategy`}
            >
              AI 사업 추진 전략
            </Button>
          </Stack>
        </Card>
      </Stack>
    </Box>
  );
}
