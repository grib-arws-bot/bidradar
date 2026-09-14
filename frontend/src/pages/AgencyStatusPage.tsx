import LaunchIcon from "@mui/icons-material/LaunchOutlined";
import {
  Box,
  Card,
  Chip,
  Link,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchAgencyChannels, type AgencyStatus } from "@/api/sources";

const STATUS_LABEL: Record<AgencyStatus, { label: string; color: "success" | "warning" | "error" | "info" | "default" }> = {
  ok: { label: "정상", color: "success" },
  warn: { label: "주의", color: "warning" },
  fail: { label: "실패", color: "error" },
  inactive: { label: "비활성", color: "default" },
  no_run_yet: { label: "수집 전", color: "default" },
  no_source: { label: "채널 미배정", color: "default" },
  running: { label: "수집 중", color: "info" },
};

// "발주기관 현황을 공고기관 중심으로"(2026-09-14 요청) — 2026-09-01 결정(발주기관 중심)의
// 반대 방향 재편. 여기는 실제로 수집을 실행하는 공고기관(채널: 나라장터·IRIS 등)을 기준으로
// 목록을 구성한다. 채널 하나를 누르면 그 채널에 딸린 발주기관 목록(상세 페이지)으로 이동한다.
// 채널 자체의 on/off·자동분석·스케줄 설정은 여전히 별도 메뉴("공고데이터 수집")의 몫이다.
export function AgencyStatusPage() {
  const navigate = useNavigate();

  const { data: channels, isLoading } = useQuery({
    queryKey: ["admin-agency-channels"],
    queryFn: fetchAgencyChannels,
  });

  return (
    <Box>
      <Typography variant="h2" sx={{ mb: 0.5 }}>
        공고기관 현황
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        실제로 공고를 수집해오는 공고기관(채널) 목록입니다. 한 채널을 누르면 그 채널로부터
        수집되는 발주기관(실제 발주 주체) 목록을 볼 수 있습니다.
      </Typography>

      <Card sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>공고기관</TableCell>
              <TableCell>수집 방식</TableCell>
              <TableCell align="right">발주기관 수</TableCell>
              <TableCell>수집 상태</TableCell>
              <TableCell>최종 수집일</TableCell>
              <TableCell>준법 확인일</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!isLoading &&
              channels?.map((row) => {
                const meta = STATUS_LABEL[row.status] ?? STATUS_LABEL.no_run_yet;
                return (
                  <TableRow
                    key={row.id}
                    hover
                    sx={{ cursor: "pointer" }}
                    onClick={() => navigate(`/admin/agencies/${row.id}`)}
                  >
                    <TableCell>
                      {row.homepage_url ? (
                        <Link
                          href={row.homepage_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}
                        >
                          {row.name}
                          <LaunchIcon sx={{ fontSize: 14 }} />
                        </Link>
                      ) : (
                        row.name
                      )}
                    </TableCell>
                    <TableCell>{row.adapter_label ?? "—"}</TableCell>
                    <TableCell align="right" className="tnum">
                      <Link component="span" underline="hover">
                        {row.org_count}
                      </Link>
                    </TableCell>
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
        {!isLoading && channels?.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ p: 3, textAlign: "center" }}>
            등록된 공고기관이 없습니다.
          </Typography>
        )}
      </Card>
    </Box>
  );
}
