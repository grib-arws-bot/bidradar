import { Box, Card, Chip, Stack, Tooltip, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

import type { MatchItem } from "@/api/customerInterests";
import { BID_STATUS_LABELS } from "@/api/notices";

// 매칭 방식 비교 페이지·"전체 신호" 결합방식 비교 팝업이 공유하는 카드/컬럼 표시 부품
// (2026-09-21, 의사결정_로그 198번 — 팝업 신설하며 MatchingComparisonPage.tsx에서 분리).

export function formatPrice(value: number | null): string {
  if (value === null) return "미공개";
  const eok = value / 100_000_000;
  return eok >= 1 ? `${eok.toFixed(1)}억원` : `${(value / 10_000).toFixed(0)}만원`;
}

// 신호 코드명 -> 화면 표시 라벨(app/services/recommendation_signals.py의 신호 이름과 맞춤).
// "rule"은 모든 프로필에 항상 있어 breakdown 맨 앞에 고정으로 보여준다.
export const SIGNAL_LABELS: Record<string, string> = {
  rule: "규칙",
  work_type: "사업유형",
  cosine_weighted: "코사인",
  sllm_confidence: "sLLM",
  a3_match: "A3",
  strategy_viewed: "전략열람",
};

// 2026-09-21 — "왜 이 점수인지 신호별로 확인할 수 있어야 한다"는 요청(CLAUDE.md S8 원칙
// "판정 근거를 붙인다"와 같은 취지). None은 "이 신호로는 평가 못 함"이지 0점이 아니므로
// 화면에서도 회색 "—"로 구분하고, 값이 있으면 0~1을 퍼센트로 보여준다.
export function SignalBreakdown({ signals }: { signals: Record<string, number | null> }) {
  const order = ["rule", "work_type", "cosine_weighted", "sllm_confidence", "a3_match", "strategy_viewed"];
  const entries = order.filter((k) => k in signals);
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
      {entries.map((key) => {
        const value = signals[key];
        return (
          <Tooltip key={key} title={value === null ? "이 신호로는 평가할 수 없는 공고(0점이 아니라 미평가)" : `${SIGNAL_LABELS[key]} 신호 값`}>
            <Chip
              label={`${SIGNAL_LABELS[key] ?? key} ${value === null ? "—" : `${Math.round(value * 100)}%`}`}
              size="small"
              variant="outlined"
              sx={{ opacity: value === null ? 0.5 : 1, fontSize: "0.7rem" }}
            />
          </Tooltip>
        );
      })}
    </Stack>
  );
}

// 요약 카드 하나 — 상세 카드(NoticeCard 등)보다 훨씬 압축해서 여러 열 비교가 한 화면에
// 들어오게 한다. bothMatched면 다른 방식에서도 나온 공고라 강조 표시(2026-09-16 사용자
// 지시 — "다른 방식에도 나오는 공고는 강조 표시").
export function MatchCard({ item, bothMatched }: { item: MatchItem; bothMatched: boolean }) {
  return (
    <Card
      variant="outlined"
      sx={{
        p: 1.5,
        flexShrink: 0, // 세로 스크롤 컨테이너 안에서 flexbox가 카드를 찌그러뜨리지 않게 고정
        borderColor: bothMatched ? "success.main" : undefined,
        bgcolor: bothMatched ? "success.50" : undefined,
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
        <Box sx={{ minWidth: 0 }}>
          <Typography
            component={RouterLink}
            to={`/notices/${item.id}`}
            variant="body2"
            sx={{ fontWeight: 600, color: "text.primary", display: "block", "&:hover": { color: "primary.main" } }}
          >
            {item.title}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {item.org_name ?? "발주기관 미상"} · {item.notice_status_label}
          </Typography>
        </Box>
        <Chip label={`${item.score}점`} size="small" color={bothMatched ? "success" : "default"} sx={{ flexShrink: 0 }} />
      </Stack>
      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
        <Chip label={BID_STATUS_LABELS[item.bid_status]} size="small" variant="outlined" />
        <Chip label={formatPrice(item.est_price)} size="small" variant="outlined" />
        {item.topics.map((t) => (
          <Chip key={t} label={t} size="small" color="primary" variant="outlined" />
        ))}
      </Stack>
      <SignalBreakdown signals={item.signals} />
    </Card>
  );
}

export function MatchColumn({
  title,
  description,
  items,
  otherIds,
  emptyHint,
}: {
  title: string;
  description: string;
  items: MatchItem[];
  otherIds: Set<number>;
  emptyHint: string;
}) {
  // 2026-09-23 사용자 지시 — 컬럼마다 따로 상하 스크롤이 생겨서 여러 컬럼을 비교하려면
  // 손이 여러 번 오가야 했다("스크롤 방식 변경해"). 컬럼 자체의 세로 스크롤(2026-09-21에
  // 넣었던 고정 높이+내부 스크롤)을 없애고 카드가 자연스러운 높이만큼 늘어나게 둔다 —
  // 세로 스크롤은 이제 ProfileScroller 바깥(페이지 전체)에서 한 번만 일어나고, 가로
  // 스크롤(컬럼 전환)만 이 안에 남는다.
  return (
    <Stack sx={{ minWidth: 320, maxWidth: 320, flexShrink: 0 }}>
      <Box sx={{ pb: 1 }}>
        <Typography variant="subtitle1" fontWeight={700}>
          {title} ({items.length}건)
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
          {description}
        </Typography>
      </Box>
      <Stack spacing={1.5} sx={{ pr: 0.5 }}>
        {items.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {emptyHint}
          </Typography>
        ) : (
          items.map((item) => <MatchCard key={item.id} item={item} bothMatched={otherIds.has(item.id)} />)
        )}
      </Stack>
    </Stack>
  );
}
