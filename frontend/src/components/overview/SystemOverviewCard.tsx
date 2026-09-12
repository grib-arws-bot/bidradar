import { Alert, Card, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { fetchSystemOverview } from "@/api/overview";

function formatGB(bytes: number): string {
  return `${(bytes / 1024 ** 3).toFixed(1)}GB`;
}

function pctColor(pct: number): string | undefined {
  return pct >= 85 ? "error.main" : undefined;
}

const CALL_TYPE_LABELS: Record<string, string> = {
  structure: "공고 AI분석(A2)",
  customer_profile: "고객 프로필 요약",
  report_commentary: "보고서 AI 코멘트",
  notice_strategy: "AI 사업 추진 전략",
};

// 카드 2: 시스템 현황(2026-09-12 재설계, ARWS의 "서버 자원" 표 구성 이식 — 항목(CPU/메모리/
// 디스크) x 열(전체/사용(BidRadar)/유휴), Docker 소켓 없이 cgroup 파일 직접 읽기). 데이터
// 수집채널 상태는 같은 날 별도 카드(ChannelStatusCard)로 분리했다(사용자 지시).
export function SystemOverviewCard() {
  const { data, isLoading } = useQuery({ queryKey: ["overview-system"], queryFn: fetchSystemOverview });

  if (isLoading || !data) {
    return (
      <Card sx={{ p: 3, height: "100%" }}>
        <Typography variant="body2" color="text.secondary">
          불러오는 중...
        </Typography>
      </Card>
    );
  }

  const { resources, llm_usage } = data;

  return (
    <Card sx={{ p: 3, height: "100%" }}>
      <Typography variant="h3" sx={{ mb: 1.5 }}>
        시스템 현황
      </Typography>

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        서버 자원
      </Typography>
      {!resources.available ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          {resources.error ?? "서버 자원 정보를 가져올 수 없습니다."}
        </Alert>
      ) : (
        <>
          <Table size="small" sx={{ mb: 0.5 }}>
            <TableHead>
              <TableRow>
                <TableCell>항목</TableCell>
                <TableCell align="right">전체</TableCell>
                <TableCell align="right">사용(BidRadar)</TableCell>
                <TableCell align="right">유휴</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell>CPU({resources.cpu!.cores}코어)</TableCell>
                <TableCell align="right" className="tnum">
                  —
                </TableCell>
                <TableCell align="right" className="tnum" sx={{ color: pctColor(resources.cpu!.host_percent) }}>
                  {resources.cpu!.host_percent.toFixed(1)}% ({resources.cpu!.container_percent.toFixed(1)}%)
                </TableCell>
                <TableCell align="right" className="tnum">
                  {(100 - resources.cpu!.host_percent).toFixed(1)}%
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell>메모리</TableCell>
                <TableCell align="right" className="tnum">
                  {formatGB(resources.memory!.host_total_bytes)}
                </TableCell>
                <TableCell align="right" className="tnum" sx={{ color: pctColor(resources.memory!.host_percent) }}>
                  <Typography component="div" variant="body2" className="tnum">
                    {resources.memory!.host_percent.toFixed(1)}% ({formatGB(resources.memory!.host_used_bytes)})
                  </Typography>
                  <Typography component="div" variant="caption" color="text.secondary" className="tnum">
                    BidRadar {formatGB(resources.memory!.container_used_bytes ?? 0)}
                    {resources.memory!.container_limit_bytes
                      ? ` / ${formatGB(resources.memory!.container_limit_bytes)}`
                      : ""}
                  </Typography>
                </TableCell>
                <TableCell align="right" className="tnum">
                  {(100 - resources.memory!.host_percent).toFixed(1)}% (
                  {formatGB(resources.memory!.host_total_bytes - resources.memory!.host_used_bytes)})
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell>디스크</TableCell>
                <TableCell align="right" className="tnum">
                  {formatGB(resources.disk!.host_total_bytes)}
                </TableCell>
                <TableCell align="right" className="tnum" sx={{ color: pctColor(resources.disk!.host_percent) }}>
                  <Typography component="div" variant="body2" className="tnum">
                    {resources.disk!.host_percent.toFixed(1)}% ({formatGB(resources.disk!.host_used_bytes)})
                  </Typography>
                  {resources.disk!.app_used_bytes != null && (
                    <Typography component="div" variant="caption" color="text.secondary" className="tnum">
                      BidRadar {formatGB(resources.disk!.app_used_bytes)}
                    </Typography>
                  )}
                </TableCell>
                <TableCell align="right" className="tnum">
                  {(100 - resources.disk!.host_percent).toFixed(1)}% (
                  {formatGB(resources.disk!.host_total_bytes - resources.disk!.host_used_bytes)})
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
            BidRadar 사용량은 DB 크기 기준(첨부파일도 DB에 저장됨) — 도커 이미지·로그·백업 파일은 포함하지 않습니다.
          </Typography>
        </>
      )}

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Claude API 사용량 — 이번 달 누적 {llm_usage.total_calls}건 · {llm_usage.total_tokens.toLocaleString()} 토큰 · $
        {llm_usage.total_cost_usd.toFixed(2)}
      </Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>호출 유형</TableCell>
            <TableCell align="right">건수</TableCell>
            <TableCell align="right">토큰</TableCell>
            <TableCell align="right">비용</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {Object.entries(llm_usage.breakdown).map(([key, v]) => (
            <TableRow key={key}>
              <TableCell>{CALL_TYPE_LABELS[key] ?? key}</TableCell>
              <TableCell align="right" className="tnum">
                {v.calls}
              </TableCell>
              <TableCell align="right" className="tnum">
                {v.tokens.toLocaleString()}
              </TableCell>
              <TableCell align="right" className="tnum">
                ${v.cost_usd.toFixed(2)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
