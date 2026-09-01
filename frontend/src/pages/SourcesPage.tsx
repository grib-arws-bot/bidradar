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

import { fetchSources } from "@/api/sources";

const STATUS_LABEL: Record<string, { label: string; color: "success" | "warning" | "error" | "default" }> = {
  ok: { label: "정상", color: "success" },
  warn: { label: "주의", color: "warning" },
  fail: { label: "실패", color: "error" },
  inactive: { label: "비활성", color: "default" },
  no_run_yet: { label: "수집 전", color: "default" },
};

// "관리자 페이지에 우리가 사용하는 데이터 소스를 기관별로 정리"(2026-09-01 요청) — 읽기 전용
// 목록. 등록·수정(probe·dryrun 등, 구현스펙 03절 전체 CRUD)은 별도 작업 단위에서 다룬다.
export function SourcesPage() {
  const { data, isLoading } = useQuery({ queryKey: ["admin-sources"], queryFn: fetchSources });

  if (isLoading || !data) {
    return <Typography>불러오는 중...</Typography>;
  }

  return (
    <Box>
      <Typography variant="h2" sx={{ mb: 0.5 }}>
        소스 관리
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        지금 연동돼 있는 데이터 소스를 기관별로 모아 보여줍니다. 총 {data.length}개 소스.
      </Typography>

      <Card sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>기관명</TableCell>
              <TableCell>소스명</TableCell>
              <TableCell>홈페이지</TableCell>
              <TableCell>수집 방식</TableCell>
              <TableCell>수집 상태</TableCell>
              <TableCell>최종 수집일</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.map((row) => {
              const meta = STATUS_LABEL[row.status] ?? STATUS_LABEL.no_run_yet;
              return (
                <TableRow key={row.id}>
                  <TableCell>{row.org_name ?? "미상"}</TableCell>
                  <TableCell>{row.name}</TableCell>
                  <TableCell>
                    {row.homepage_url ? (
                      <Link href={row.homepage_url} target="_blank" rel="noreferrer" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                        바로가기
                        <LaunchIcon sx={{ fontSize: 14 }} />
                      </Link>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        —
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>{row.adapter_label}</TableCell>
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
      </Card>
    </Box>
  );
}
