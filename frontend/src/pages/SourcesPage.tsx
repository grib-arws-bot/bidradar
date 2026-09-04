import LaunchIcon from "@mui/icons-material/LaunchOutlined";
import {
  Box,
  Card,
  Chip,
  Link,
  MenuItem,
  Pagination,
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
import { useState } from "react";

import { fetchAgencies, fetchAgencyCategories, fetchSources, updateAutoExtract, type AgencyStatus } from "@/api/sources";

const AGENCY_PAGE_SIZE = 50;

const STATUS_LABEL: Record<AgencyStatus, { label: string; color: "success" | "warning" | "error" | "default" }> = {
  ok: { label: "정상", color: "success" },
  warn: { label: "주의", color: "warning" },
  fail: { label: "실패", color: "error" },
  inactive: { label: "비활성", color: "default" },
  no_run_yet: { label: "수집 전", color: "default" },
  no_source: { label: "채널 미배정", color: "default" },
};

// "관리자 페이지 소스 관리를 발주기관 중심으로"(2026-09-01 요청) — 조달청·IRIS는 발주기관이
// 아니라 공고기관(수집 채널)이라는 지적에 따라, 여기는 실제 발주기관(org)을 기준으로 목록을
// 구성하고 그 기관이 어느 채널로 수집되는지만 붙여 보여준다. 발주기관이 계속 늘어날 것을
// 전제로 검색·필터를 둔다.
export function SourcesPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<AgencyStatus | "">("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();

  // 필터가 바뀌면 이전 필터 기준 페이지 번호가 새 결과에서 의미가 없어지니 1페이지로 되돌린다.
  const updateFilters = (next: { q?: string; status?: AgencyStatus | ""; category?: string }) => {
    if ("q" in next) setQ(next.q ?? "");
    if ("status" in next) setStatus(next.status ?? "");
    if ("category" in next) setCategory(next.category ?? "");
    setPage(1);
  };

  const { data, isLoading } = useQuery({
    queryKey: ["admin-agencies", q, status, category, page],
    queryFn: () =>
      fetchAgencies({
        q: q || undefined,
        status: (status as AgencyStatus) || undefined,
        category: category || undefined,
        page,
        size: AGENCY_PAGE_SIZE,
      }),
  });

  const { data: categories } = useQuery({
    queryKey: ["admin-agency-categories"],
    queryFn: fetchAgencyCategories,
  });

  const { data: sources, isLoading: sourcesLoading } = useQuery({
    queryKey: ["admin-sources"],
    queryFn: fetchSources,
  });

  const autoExtractMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => updateAutoExtract(id, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-sources"] }),
  });

  const pageCount = Math.max(1, Math.ceil((data?.total ?? 0) / AGENCY_PAGE_SIZE));

  return (
    <Box>
      <Typography variant="h2" sx={{ mb: 0.5 }}>
        데이터 소스
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        실제로 데이터가 수집되고 있는 발주기관 목록입니다(2026-09-03, 가짜/미연결 항목 정리).
        조달청·IRIS 같은 이름은 발주기관이 아니라 공고기관(수집 채널)이라 "공고기관" 열에만
        나타납니다.
      </Typography>

      <Typography variant="h3" sx={{ mb: 0.5, fontSize: 18 }}>
        수집 채널 — 첨부문서 자동 분석
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        켜두면 이 채널에서 새 공고를 수집할 때마다 첨부문서를 자동으로 내려받아 텍스트를
        추출합니다(S8 A1, 충족 판정 아님). 나라장터처럼 건수가 많은 채널은 꺼둔 채로
        공고 상세페이지에서 수동으로 실행하는 것을 권장합니다.
      </Typography>
      <Card sx={{ overflowX: "auto", mb: 3 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>채널명</TableCell>
              <TableCell>공고 단계</TableCell>
              <TableCell>수집 방식</TableCell>
              <TableCell align="right">첨부문서 자동 분석</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!sourcesLoading &&
              sources?.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{row.name}</TableCell>
                  <TableCell>{row.stage}</TableCell>
                  <TableCell>{row.adapter_label}</TableCell>
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
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </Card>

      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 2 }}>
        <TextField
          size="small"
          label="기관명·약자 검색"
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
              <TableCell>공고기관</TableCell>
              <TableCell>수집 방식</TableCell>
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
                    <TableCell>{row.name}</TableCell>
                    <TableCell>{row.abbr ?? "—"}</TableCell>
                    <TableCell>{row.category ?? "—"}</TableCell>
                    <TableCell>
                      {row.channel ? (
                        row.channel_url ? (
                          <Link
                            href={row.channel_url}
                            target="_blank"
                            rel="noreferrer"
                            sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}
                          >
                            {row.channel}
                            <LaunchIcon sx={{ fontSize: 14 }} />
                          </Link>
                        ) : (
                          row.channel
                        )
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>{row.adapter_label ?? "—"}</TableCell>
                    <TableCell>
                      <Chip label={meta.label} size="small" color={meta.color} />
                    </TableCell>
                    <TableCell className="tnum">
                      {row.last_run_at ? new Date(row.last_run_at).toLocaleString("ko-KR") : "수집 이력 없음"}
                    </TableCell>
                    {/* 준법 확인일(advisory INBOX #6) — 채널이 없는 행(no_source)은 확인 대상이
                        아니므로 배지 없이 "—"만 보여준다. 90일 지나면 경고색으로 눈에 띄게. */}
                    <TableCell className="tnum">
                      {row.channel === null ? (
                        "—"
                      ) : (
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
                      )}
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
