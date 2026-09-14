import ArrowBackIcon from "@mui/icons-material/ArrowBackOutlined";
import LaunchIcon from "@mui/icons-material/LaunchOutlined";
import {
  Box,
  Card,
  Chip,
  Link,
  MenuItem,
  Pagination,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";

import { fetchAgencies, fetchAgencyCategories, fetchAgencyChannels, type AgencyStatus } from "@/api/sources";

const AGENCY_PAGE_SIZE = 50;

const STATUS_LABEL: Record<AgencyStatus, { label: string; color: "success" | "warning" | "error" | "info" | "default" }> = {
  ok: { label: "정상", color: "success" },
  warn: { label: "주의", color: "warning" },
  fail: { label: "실패", color: "error" },
  inactive: { label: "비활성", color: "default" },
  no_run_yet: { label: "수집 전", color: "default" },
  no_source: { label: "채널 미배정", color: "default" },
  running: { label: "수집 중", color: "info" },
};

// 공고기관(채널) 상세 — "공고기관 현황"(AgencyStatusPage)에서 채널 하나를 눌렀을 때 오는
// 화면(2026-09-14 신설). 그 채널로부터 수집되는 발주기관 목록만 보여준다 — 이전에는
// 발주기관 화면 전체가 이 내용(채널 필터 없이 전체)이었다.
export function AgencyChannelDetailPage() {
  const { sourceId } = useParams<{ sourceId: string }>();
  const sourceIdNum = Number(sourceId);

  const [q, setQ] = useState("");
  const [status, setStatus] = useState<AgencyStatus | "">("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);

  const updateFilters = (next: { q?: string; status?: AgencyStatus | ""; category?: string }) => {
    if ("q" in next) setQ(next.q ?? "");
    if ("status" in next) setStatus(next.status ?? "");
    if ("category" in next) setCategory(next.category ?? "");
    setPage(1);
  };

  // 채널 자체의 이름·상태 등 헤더 정보는 별도 엔드포인트 없이 채널 목록에서 찾아 쓴다
  // (채널이 16개 안팎이라 목록 전체를 한 번 더 불러와도 비용이 무시할 만함).
  const { data: channels } = useQuery({
    queryKey: ["admin-agency-channels"],
    queryFn: fetchAgencyChannels,
  });
  const channel = channels?.find((c) => c.id === sourceIdNum);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-agencies", sourceIdNum, q, status, category, page],
    queryFn: () =>
      fetchAgencies({
        source_id: sourceIdNum,
        q: q || undefined,
        status: (status as AgencyStatus) || undefined,
        category: category || undefined,
        page,
        size: AGENCY_PAGE_SIZE,
      }),
    enabled: Number.isFinite(sourceIdNum),
  });

  const { data: categories } = useQuery({
    queryKey: ["admin-agency-categories"],
    queryFn: fetchAgencyCategories,
  });

  const pageCount = Math.max(1, Math.ceil((data?.total ?? 0) / AGENCY_PAGE_SIZE));

  return (
    <Box>
      <Link
        component={RouterLink}
        to="/admin/agencies"
        sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, mb: 1.5, fontSize: 13 }}
      >
        <ArrowBackIcon sx={{ fontSize: 16 }} />
        공고기관 현황으로
      </Link>

      <Typography variant="h2" sx={{ mb: 0.5 }}>
        {channel?.name ?? "공고기관"}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        {channel?.homepage_url ? (
          <Link href={channel.homepage_url} target="_blank" rel="noreferrer" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
            {channel.homepage_url}
            <LaunchIcon sx={{ fontSize: 13 }} />
          </Link>
        ) : (
          "이 공고기관(채널)이 수집해오는 발주기관 목록입니다."
        )}
      </Typography>

      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 2 }}>
        <TextField
          size="small"
          label="발주기관명·약자 검색"
          value={q}
          onChange={(e) => updateFilters({ q: e.target.value })}
          sx={{ minWidth: 220 }}
        />
        <TextField
          size="small"
          select
          label="수집 상태"
          value={status}
          onChange={(e) => updateFilters({ status: e.target.value as AgencyStatus | "" })}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">전체</MenuItem>
          {Object.entries(STATUS_LABEL).map(([value, meta]) => (
            <MenuItem key={value} value={value}>
              {meta.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          select
          label="분류"
          value={category}
          onChange={(e) => updateFilters({ category: e.target.value })}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">전체</MenuItem>
          {categories?.map((c) => (
            <MenuItem key={c} value={c}>
              {c}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      <Card sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>발주기관</TableCell>
              <TableCell>기관약자</TableCell>
              <TableCell>분류</TableCell>
              <TableCell>수집 상태</TableCell>
              <TableCell>최종 수집일</TableCell>
              <TableCell>준법 확인일</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!isLoading &&
              data?.items.map((row) => {
                const meta = STATUS_LABEL[row.status] ?? STATUS_LABEL.no_source;
                return (
                  <TableRow key={row.id}>
                    <TableCell>
                      {row.org_homepage_url ? (
                        <Link
                          href={row.org_homepage_url}
                          target="_blank"
                          rel="noreferrer"
                          sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}
                        >
                          {row.name}
                          <LaunchIcon sx={{ fontSize: 13 }} />
                        </Link>
                      ) : (
                        row.name
                      )}
                    </TableCell>
                    <TableCell>{row.abbr ?? "—"}</TableCell>
                    <TableCell>{row.category ?? "—"}</TableCell>
                    <TableCell>
                      <Chip label={meta.label} size="small" color={meta.color} />
                    </TableCell>
                    <TableCell className="tnum">
                      {row.last_run_at ? new Date(row.last_run_at).toLocaleString("ko-KR") : "수집 이력 없음"}
                    </TableCell>
                    <TableCell className="tnum">
                      <Chip
                        label={
                          row.legal_verified_at
                            ? new Date(row.legal_verified_at).toLocaleDateString("ko-KR")
                            : "확인 이력 없음"
                        }
                        size="small"
                        color={row.compliance_overdue ? "warning" : "default"}
                        variant={row.compliance_overdue ? "filled" : "outlined"}
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
          </TableBody>
        </Table>
        {!isLoading && data?.items.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ p: 3, textAlign: "center" }}>
            조건에 맞는 발주기관이 없습니다.
          </Typography>
        )}
      </Card>
      {!isLoading && data && data.total > AGENCY_PAGE_SIZE && (
        <Stack alignItems="center" sx={{ mt: 2 }}>
          <Pagination count={pageCount} page={page} onChange={(_, value) => setPage(value)} />
        </Stack>
      )}
    </Box>
  );
}
