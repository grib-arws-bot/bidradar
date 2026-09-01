import LaunchIcon from "@mui/icons-material/LaunchOutlined";
import {
  Box,
  Card,
  Chip,
  Link,
  MenuItem,
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
import { useMemo, useState } from "react";

import { fetchAgencies, type AgencyStatus } from "@/api/sources";

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

  const { data, isLoading } = useQuery({
    queryKey: ["admin-agencies", q, status, category],
    queryFn: () =>
      fetchAgencies({
        q: q || undefined,
        status: (status as AgencyStatus) || undefined,
        category: category || undefined,
      }),
  });

  const categories = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.map((r) => r.category).filter((c): c is string => !!c))).sort();
  }, [data]);

  return (
    <Box>
      <Typography variant="h2" sx={{ mb: 0.5 }}>
        소스 관리
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        추적 중인 발주기관 목록입니다. 조달청·IRIS 같은 이름은 발주기관이 아니라 공고기관(수집
        채널)이라 "공고기관" 열에만 나타납니다.
      </Typography>

      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 2 }}>
        <TextField
          size="small"
          label="기관명·약자 검색"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          sx={{ minWidth: 220 }}
        />
        <TextField
          size="small"
          select
          label="수집 상태"
          value={status}
          onChange={(e) => setStatus(e.target.value as AgencyStatus | "")}
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
          onChange={(e) => setCategory(e.target.value)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">전체</MenuItem>
          {categories.map((c) => (
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
              <TableCell>공고 URL</TableCell>
              <TableCell>수집 방식</TableCell>
              <TableCell>수집 상태</TableCell>
              <TableCell>최종 수집일</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!isLoading &&
              data?.map((row) => {
                const meta = STATUS_LABEL[row.status] ?? STATUS_LABEL.no_source;
                return (
                  <TableRow key={row.id}>
                    <TableCell>{row.name}</TableCell>
                    <TableCell>{row.abbr ?? "—"}</TableCell>
                    <TableCell>{row.category ?? "—"}</TableCell>
                    <TableCell>{row.channel ?? "—"}</TableCell>
                    <TableCell>
                      {row.notice_url ? (
                        <Link href={row.notice_url} target="_blank" rel="noreferrer" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                          바로가기
                          <LaunchIcon sx={{ fontSize: 14 }} />
                        </Link>
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
                  </TableRow>
                );
              })}
          </TableBody>
        </Table>
        {!isLoading && data?.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ p: 3, textAlign: "center" }}>
            조건에 맞는 발주기관이 없습니다.
          </Typography>
        )}
      </Card>
    </Box>
  );
}
