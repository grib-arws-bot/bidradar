import { Box, Card, Chip, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { Link as RouterLink } from "react-router-dom";

import { fetchOverview } from "@/api/overview";

const STATUS_LABEL: Record<string, { label: string; color: "success" | "warning" | "error" | "default" }> = {
  ok: { label: "정상", color: "success" },
  warn: { label: "주의", color: "warning" },
  fail: { label: "실패", color: "error" },
  inactive: { label: "비활성", color: "default" },
  no_run_yet: { label: "수집 전", color: "default" },
};

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <Stack direction="row" justifyContent="space-between" alignItems="baseline">
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body1" fontWeight={700} className="tnum">
        {value}
      </Typography>
    </Stack>
  );
}

function SummaryCard({
  title,
  headline,
  headlineSub,
  children,
}: {
  title: string;
  headline: string | number;
  headlineSub?: string;
  children: React.ReactNode;
}) {
  return (
    <Card sx={{ p: 2.5 }}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
        {title}
      </Typography>
      <Typography variant="h2" className="tnum">
        {headline}
      </Typography>
      {headlineSub && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
          {headlineSub}
        </Typography>
      )}
      <Stack spacing={0.5} sx={{ mt: 1.5 }}>
        {children}
      </Stack>
    </Card>
  );
}

// "전체 시스템 운영을 위한 관리자 페이지"(2026-09-01 요청) — 로그인 후 첫 화면.
// 4개 카드 2x2 배열(2026-09-05 요청): 공고 데이터·등록된 고객·보고서 생성 현황·시스템 현황.
// 카드 내용은 Phase 1 흐름(공고 수집 → 고객 분석 → 보고서 최적화 → 발송)에서 각 단계가
// 지금 얼마나 진행됐는지 한눈에 보이도록 골랐다.
export function OverviewPage() {
  const { data, isLoading } = useQuery({ queryKey: ["overview"], queryFn: fetchOverview });

  if (isLoading || !data) {
    return <Typography>불러오는 중...</Typography>;
  }

  const tierLabel = (tier: string) => (tier === "internal" ? "그립 자신" : tier);

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h2">전체 현황</Typography>
        <Typography variant="body2" color="text.secondary">
          공고 탐색으로 가기 전에, 시스템이 지금 어떻게 돌아가고 있는지 한눈에.
        </Typography>
      </Box>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
          gap: 2,
        }}
      >
        <SummaryCard
          title="공고 데이터"
          headline={data.notices.total}
          headlineSub={`최근 7일 +${data.notices.added_7d} · 최근 24시간 +${data.notices.added_24h}`}
        >
          <Stat label="입찰 접수중" value={data.notices.in_progress} />
          <Stat label="마감" value={data.notices.closed} />
          <Stat label="첨부 분석 대기(A1)" value={data.pending_analysis.extraction} />
          <Stat label="AI 분석 대기(A2)" value={data.pending_analysis.analyze} />
        </SummaryCard>

        <SummaryCard
          title="등록된 고객"
          headline={data.customers.total}
          headlineSub={Object.entries(data.customers.by_tier)
            .map(([tier, n]) => `${tierLabel(tier)} ${n}`)
            .join(" · ")}
        >
          <Stat label="관심주제 설정 완료" value={data.customers.with_interests} />
          <Stat label="AI 프로필 요약 완료" value={data.customers.profile_summarized} />
        </SummaryCard>

        <SummaryCard
          title="보고서 생성 현황"
          headline={data.reports.total}
          headlineSub={`최근 7일 +${data.reports.added_7d}`}
        >
          <Stat label="AI 코멘트 적용" value={data.reports.with_ai_commentary} />
          <Stat label="누적 조회수" value={data.reports.total_views} />
        </SummaryCard>

        <SummaryCard
          title="시스템 현황"
          headline={data.sources.total}
          headlineSub={
            data.sources.last_run_at
              ? `최근 수집 ${new Date(data.sources.last_run_at).toLocaleString("ko-KR")}`
              : "수집 이력 없음"
          }
        >
          <Stat label="정상" value={data.sources.counts.ok ?? 0} />
          <Stat label="주의" value={data.sources.counts.warn ?? 0} />
          <Stat label="실패" value={data.sources.counts.fail ?? 0} />
          <Stat label="비활성" value={data.sources.counts.inactive ?? 0} />
        </SummaryCard>
      </Box>

      <Card sx={{ p: 3 }}>
        <Typography variant="h3" sx={{ mb: 1.5 }}>
          소스 상태
        </Typography>
        <Stack spacing={1}>
          {data.sources.sources.map((s) => {
            const meta = STATUS_LABEL[s.status] ?? STATUS_LABEL.no_run_yet;
            return (
              <Stack key={s.id} direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="body2">{s.name}</Typography>
                <Stack direction="row" spacing={1.5} alignItems="center">
                  <Typography variant="caption" color="text.secondary">
                    {s.last_run_at ? new Date(s.last_run_at).toLocaleString("ko-KR") : "수집 이력 없음"}
                  </Typography>
                  <Chip label={meta.label} size="small" color={meta.color} />
                </Stack>
              </Stack>
            );
          })}
        </Stack>
      </Card>

      <Card sx={{ p: 3 }}>
        <Typography variant="h3" sx={{ mb: 1.5 }}>
          최근 생성된 리포트
        </Typography>
        <Stack spacing={1}>
          {data.recent_reports.map((r) => (
            <Stack key={r.id} direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="body2">
                {r.customer_name} · {new Date(r.generated_at).toLocaleString("ko-KR")}
              </Typography>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <Typography variant="caption" color="text.secondary">
                  조회 {r.view_count}회
                </Typography>
                <RouterLink to={`/r/${r.token}`} target="_blank" rel="noreferrer">
                  <Typography variant="caption" color="primary.main">
                    미리보기 →
                  </Typography>
                </RouterLink>
              </Stack>
            </Stack>
          ))}
          {data.recent_reports.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              아직 생성된 리포트가 없습니다. "보고서 관리" 화면에서 만들 수 있습니다.
            </Typography>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}
