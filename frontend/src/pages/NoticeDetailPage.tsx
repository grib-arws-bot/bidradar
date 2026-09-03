import ArrowBackIcon from "@mui/icons-material/ArrowBackIosNewOutlined";
import ArrowForwardIcon from "@mui/icons-material/ArrowForwardIosOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import NotificationsOutlinedIcon from "@mui/icons-material/NotificationsOutlined";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import OpenInNewIcon from "@mui/icons-material/OpenInNewOutlined";
import {
  Box,
  Button,
  Card,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  Link,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { followOrg } from "@/api/classification";
import { EXTRA_FIELD_LABELS, fetchNeighbors, fetchNoticeDetail, formatExtraValue } from "@/api/notices";

export function NoticeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const noticeId = Number(id);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const detailQuery = useQuery({
    queryKey: ["notice", noticeId],
    queryFn: () => fetchNoticeDetail(noticeId),
  });

  // 이전/다음이 목록의 필터·정렬 순서를 이어서 이동(S1-d) — 카드에서 넘어올 때 붙여온
  // 쿼리스트링을 그대로 재사용해서 neighbors를 조회한다.
  const neighborsQuery = useQuery({
    queryKey: ["notice-neighbors", noticeId, searchParams.toString()],
    queryFn: () => fetchNeighbors(noticeId, searchParams),
  });

  const followMutation = useMutation({
    mutationFn: () => followOrg(noticeId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notice", noticeId] }),
  });

  if (detailQuery.isLoading) {
    return (
      <Stack alignItems="center" sx={{ py: 8 }}>
        <CircularProgress />
      </Stack>
    );
  }

  if (!detailQuery.data) {
    return <Typography>공고를 찾을 수 없습니다.</Typography>;
  }

  const notice = detailQuery.data;
  const qs = searchParams.toString();

  return (
    <Stack spacing={3} sx={{ maxWidth: 860 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Button component={RouterLink} to={`/notices?${qs}`} size="small">
          ← 목록으로
        </Button>
        <Stack direction="row" spacing={1} alignItems="center">
          <Tooltip title="이전 (현재 필터·정렬 기준)">
            <span>
              <IconButton
                size="small"
                disabled={!neighborsQuery.data?.prev_id}
                onClick={() => navigate(`/notices/${neighborsQuery.data?.prev_id}?${qs}`)}
              >
                <ArrowBackIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="다음 (현재 필터·정렬 기준)">
            <span>
              <IconButton
                size="small"
                disabled={!neighborsQuery.data?.next_id}
                onClick={() => navigate(`/notices/${neighborsQuery.data?.next_id}?${qs}`)}
              >
                <ArrowForwardIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </Stack>

      <Card sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" useFlexGap>
            <Box>
              <Stack direction="row" spacing={0.75} sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
                <Chip label={notice.stage} size="small" color="secondary" variant="outlined" />
                {notice.biz_type && <Chip label={notice.biz_type} size="small" variant="outlined" />}
                {notice.work_type && <Chip label={notice.work_type} size="small" variant="outlined" />}
              </Stack>
              <Typography variant="h2">{notice.title}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                {notice.org_name ?? "발주기관 미상"} · {notice.region ?? "지역 미상"}
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} alignItems="center">
              <Button
                variant="outlined"
                size="small"
                startIcon={<OpenInNewIcon fontSize="small" />}
                component={Link}
                href={notice.url}
                target="_blank"
                rel="noreferrer"
              >
                원문 보기
              </Button>
              <Button
                variant={notice.org_followed ? "contained" : "outlined"}
                size="small"
                startIcon={notice.org_followed ? <NotificationsActiveIcon /> : <NotificationsOutlinedIcon />}
                disabled={followMutation.isPending || notice.org_followed}
                onClick={() => followMutation.mutate()}
              >
                {notice.org_followed ? "팔로우 중" : "이 기관 팔로우"}
              </Button>
            </Stack>
          </Stack>

          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
            <Field label="공고번호" value={notice.notice_no ?? "미부여"} />
            <Field label="추정가격" value={notice.est_price ? `${(notice.est_price / 100_000_000).toFixed(1)}억원` : "미공개"} />
            <Field label="게시일" value={notice.open_dt ? new Date(notice.open_dt).toLocaleDateString("ko-KR") : "-"} />
            <Field label="마감일" value={notice.close_dt ? new Date(notice.close_dt).toLocaleString("ko-KR") : "마감일 미공개"} />
            {notice.assignee_name && <Field label="담당자" value={notice.assignee_name} />}
          </Stack>

          {notice.scores.length > 0 && (
            <Box>
              <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
                매칭된 관심 분야
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {notice.scores.map((s) => (
                  <Chip key={s.interest_topic_id} label={`${s.name} (+${s.l2_score})`} size="small" />
                ))}
              </Stack>
            </Box>
          )}
        </Stack>
      </Card>

      {notice.requirements.length > 0 && (
        <Card sx={{ p: 3 }}>
          <Typography variant="h3" sx={{ mb: 1.5 }}>
            참여 자격 요건
          </Typography>
          <Stack spacing={1}>
            {notice.requirements.map((req) => (
              <Stack
                key={req.id}
                direction="row"
                spacing={1.5}
                sx={{
                  p: 1,
                  borderRadius: 1,
                  bgcolor: req.we_qualify === false ? "error.lighter" : "transparent",
                }}
              >
                <Chip label={req.type} size="small" />
                <Typography
                  variant="body2"
                  sx={{ color: req.we_qualify === false ? "error.main" : "text.primary", fontWeight: req.we_qualify === false ? 600 : 400 }}
                >
                  {req.value}
                  {req.we_qualify === false && " — 미충족"}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </Card>
      )}

      {notice.extra && Object.keys(notice.extra).length > 0 && (
        <Card sx={{ p: 3 }}>
          <Typography variant="h3" sx={{ mb: 1.5 }}>
            추가 정보
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
            이 소스가 제공하는 원본 필드 그대로입니다 — 목록 응답에 담당자 개인정보는 없습니다.
          </Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2 }}>
            {Object.entries(notice.extra).map(([key, value]) => (
              <Box key={key} sx={{ minWidth: 0 }}>
                <Typography variant="caption" color="text.secondary">
                  {EXTRA_FIELD_LABELS[key] ?? key}
                </Typography>
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                  {formatExtraValue(key, value)}
                </Typography>
              </Box>
            ))}
          </Box>
        </Card>
      )}

      <Divider />

      <Tooltip title="심층 분석은 다음 작업 단위(U9)에서 제공됩니다">
        <span>
          <Button variant="contained" startIcon={<AutoAwesomeOutlinedIcon />} disabled>
            심층 분석 실행
          </Button>
        </span>
      </Tooltip>
    </Stack>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" className="tnum" fontWeight={600}>
        {value}
      </Typography>
    </Box>
  );
}
