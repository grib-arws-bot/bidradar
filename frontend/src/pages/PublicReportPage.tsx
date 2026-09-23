import { Box, Card, Chip, CircularProgress, Stack, Tab, Tabs, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";

import { BID_STATUS_LABELS } from "@/api/notices";
import { fetchPublicReport, recordPublicNoticeClick, type ReportNoticeItem } from "@/api/reports";
import Logo from "@/components/Logo";

// 리포트 3단계 섹션(2026-09-07 사용자 지시) — 백엔드(customer_interest.py _section_of)와
// 같은 분류를 프런트에서 다시 계산한다(저장 스냅샷 스키마는 그대로 flat 목록이라 백엔드가
// 이미 섹션별 상한을 지켜 골라둔 결과를 그룹으로 나눠 보여주기만 하면 됨).
type Section = "plan" | "prenotice" | "active";
const SECTION_ORDER: Section[] = ["active", "prenotice", "plan"];
const SECTION_LABELS: Record<Section, string> = {
  plan: "발주계획",
  prenotice: "사전규격 · 접수예정",
  active: "입찰접수 · 접수중",
};

function sectionOf(n: ReportNoticeItem): Section {
  if (n.stage === "발주계획") return "plan";
  if (n.stage === "사전규격") return "prenotice";
  // "!== in_progress"로 걸렀더니 이미 접수 마감(closed)된 건까지 "접수예정"으로 잘못
  // 분류되는 버그가 실제 리포트에서 발견됨(2026-09-07) — 접수 시작 전(upcoming·
  // unscheduled)일 때만 예정으로 본다.
  if (n.notice_type === "정부지원" && (n.bid_status === "upcoming" || n.bid_status === "unscheduled")) return "prenotice";
  return "active";
}

function formatPrice(value: number | null): string {
  if (value === null) return "미공개";
  const eok = value / 100_000_000;
  return eok >= 1 ? `${eok.toFixed(1)}억원` : `${(value / 10_000).toFixed(0)}만원`;
}

// NoticeCard.tsx(내부 공고 탐색)와 같은 D-day 계산 — 자정 기준으로 깎아 비교해야
// "오늘 마감"이 정확히 D-0으로 나온다.
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

// 내부 공고 탐색(NoticeCard.tsx)과 최대한 같은 정보 구성으로 보여준다(2026-09-05 요청) —
// 배지 한 줄 + 제목(공고 상세로 링크) + 발주기관/지역/공고번호 + 사업비·D-day 강조.
function PublicNoticeCard({ notice, token }: { notice: ReportNoticeItem; token: string }) {
  const dday = ddayInfo(notice.close_dt);
  return (
    <Card variant="outlined" sx={{ p: 2, height: "100%" }}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1} sx={{ mb: 1 }}>
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
          <Chip label={notice.notice_type} size="small" color="secondary" variant="outlined" />
          <Chip label={notice.notice_status_label} size="small" variant="outlined" />
          <Chip label={notice.work_type_label} size="small" variant="outlined" />
        </Stack>
        <Chip
          label={BID_STATUS_LABELS[notice.bid_status]}
          size="small"
          color={notice.bid_status === "in_progress" ? "error" : "default"}
          variant={notice.bid_status === "in_progress" ? "filled" : "outlined"}
          sx={{ fontWeight: 700, flexShrink: 0 }}
        />
      </Stack>

      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
        <Box sx={{ minWidth: 0 }}>
          <Typography
            variant="h3"
            component={RouterLink}
            to={`/r/${token}/notices/${notice.id}`}
            // 행동 데이터 수집(2026-09-23) — 클릭 자체가 실패해도 이동은 막지 않는다(부가
            // 신호일 뿐 필수 UX 아님, catch 없이 무시).
            onClick={() => {
              void recordPublicNoticeClick(token, notice.id);
            }}
            sx={{ display: "block", mb: 0.5, color: "text.primary", "&:hover": { color: "primary.main" } }}
          >
            {notice.title}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {notice.org_name ?? "발주기관 미상"}
            {notice.region ? ` · ${notice.region}` : ""}
            {notice.notice_no ? ` · ${notice.notice_no}` : ""}
          </Typography>
          <Typography variant="body2" color="text.secondary" className="tnum" sx={{ mt: 0.25 }}>
            게시 {notice.open_dt ? new Date(notice.open_dt).toLocaleDateString("ko-KR") : "미상"} · 마감{" "}
            {notice.close_dt ? new Date(notice.close_dt).toLocaleDateString("ko-KR") : "미상"}
          </Typography>
          {/* 이 공고가 왜 관심공고로 떴는지(어느 관심주제와 일치했는지, 2026-09-06 요청) */}
          {notice.topics && notice.topics.length > 0 && (
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
              {notice.topics.map((topic) => (
                <Chip key={topic} label={topic} size="small" color="primary" variant="outlined" />
              ))}
            </Stack>
          )}
        </Box>
        <Stack alignItems="flex-end" spacing={0.5} sx={{ flexShrink: 0 }}>
          <Typography variant="h3" className="tnum" fontWeight={700} color="primary.main" sx={{ whiteSpace: "nowrap" }}>
            {formatPrice(notice.est_price)}
          </Typography>
          {dday && (
            <Chip label={dday.label} size="medium" color={dday.urgent ? "error" : "warning"} variant="filled" sx={{ fontWeight: 700 }} />
          )}
        </Stack>
      </Stack>

      {notice.ai_commentary && (
        <Box sx={{ mt: 1.5, p: 1, borderRadius: 1, bgcolor: "action.hover" }}>
          <Typography variant="body2">{notice.ai_commentary}</Typography>
          {notice.ai_strategy && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              참고: {notice.ai_strategy}
            </Typography>
          )}
        </Box>
      )}
    </Card>
  );
}

// 로그인 없는 서명된 공유 링크(의사결정_로그 8·9번) — 외부 고객이 이메일의 "상세보기"를 눌러
// 도착하는 화면. DashboardLayout(사이드바·계정) 없이 이 페이지 하나만 독립적으로 보여준다.
export function PublicReportPage() {
  const { token } = useParams<{ token: string }>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["public-report", token],
    queryFn: () => fetchPublicReport(token!),
    retry: false,
  });
  const [activeSection, setActiveSection] = useState<Section | null>(null);

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
        <Typography>리포트를 찾을 수 없습니다. 링크가 만료되었을 수 있습니다.</Typography>
      </Box>
    );
  }

  const grouped: Record<Section, ReportNoticeItem[]> = { plan: [], prenotice: [], active: [] };
  for (const n of data.notices) grouped[sectionOf(n)].push(n);
  // 기본 탭은 "입찰접수·접수중"(가장 급한 것) 우선, 없으면 다음 순서로 — 빈 리포트여도
  // 항상 "입찰접수·접수중" 탭이 보이게 그 경우만 예외로 둔다.
  const section = activeSection ?? SECTION_ORDER.find((s) => grouped[s].length > 0) ?? "active";
  const currentNotices = grouped[section];

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default", py: { xs: 3, md: 6 } }}>
      <Stack spacing={3} sx={{ maxWidth: 1100, mx: "auto", px: 2 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Logo size={34} />
          <Chip label={data.customer_name} size="small" sx={{ ml: "auto" }} />
        </Stack>

        <Card sx={{ p: 3 }}>
          <Typography variant="h2">관심 공고</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {new Date(data.generated_at).toLocaleDateString("ko-KR")} 기준 · 총 {data.summary.total}건
            {data.summary.closing_soon > 0 && ` · 7일 내 마감 ${data.summary.closing_soon}건`}
          </Typography>

          {data.notices.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              관심 조건에 맞는 공고가 없었습니다.
            </Typography>
          ) : (
            <>
              <Tabs
                value={section}
                onChange={(_, next: Section) => setActiveSection(next)}
                sx={{ mb: 2, minHeight: 0, borderBottom: 1, borderColor: "divider" }}
              >
                {/* 2026-09-15 — 발주계획은 매칭 대상에서 아예 제외돼(백엔드 customer_interest.py
                    _candidate_notices) 새 리포트엔 항상 0건이라, 그 탭을 계속 보여주면 "왜
                    맨날 0건이지" 하는 오해를 살 수 있다. 0건인 섹션은 탭 자체를 숨긴다 — 예전에
                    생성된 리포트에 아직 발주계획 항목이 남아있으면(스냅샷이라 재계산 안 됨)
                    그 경우엔 그대로 보인다. */}
                {SECTION_ORDER.filter((s) => grouped[s].length > 0).map((s) => (
                  <Tab key={s} value={s} label={`${SECTION_LABELS[s]} (${grouped[s].length})`} sx={{ minHeight: 0 }} />
                ))}
              </Tabs>

              {/* 카드를 가로형 2열로(2026-09-07 요청) — 좁은 화면(모바일)에선 1열로 접힌다. */}
              <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 1.5 }}>
                {currentNotices.map((n) => (
                  <PublicNoticeCard key={n.id} notice={n} token={token!} />
                ))}
              </Box>
              {currentNotices.length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  이 단계에 해당하는 공고가 없습니다.
                </Typography>
              )}
            </>
          )}
        </Card>

        <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
          <RouterLink to={`/r/${token}/sources`} style={{ color: "inherit" }}>
            데이터 출처 안내
          </RouterLink>
        </Typography>
      </Stack>
    </Box>
  );
}
