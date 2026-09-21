import ChevronLeftIcon from "@mui/icons-material/ChevronLeftOutlined";
import ChevronRightIcon from "@mui/icons-material/ChevronRightOutlined";
import { Alert, Box, Button, Card, Chip, CircularProgress, IconButton, MenuItem, Stack, TextField, Tooltip, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link as RouterLink } from "react-router-dom";

import {
  fetchCustomers,
  fetchInterestMatchesCompare,
  type MatchItem,
} from "@/api/customerInterests";
import { BID_STATUS_LABELS } from "@/api/notices";
import { apiErrorMessage } from "@/utils/errors";

function formatPrice(value: number | null): string {
  if (value === null) return "미공개";
  const eok = value / 100_000_000;
  return eok >= 1 ? `${eok.toFixed(1)}억원` : `${(value / 10_000).toFixed(0)}만원`;
}

// 신호 코드명 -> 화면 표시 라벨(app/services/recommendation_signals.py의 신호 이름과 맞춤).
// "rule"은 모든 프로필에 항상 있어 breakdown 맨 앞에 고정으로 보여준다.
const SIGNAL_LABELS: Record<string, string> = {
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
function SignalBreakdown({ signals }: { signals: Record<string, number | null> }) {
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
function MatchCard({ item, bothMatched }: { item: MatchItem; bothMatched: boolean }) {
  return (
    <Card
      variant="outlined"
      sx={{
        p: 1.5,
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

function MatchColumn({
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
  // 2026-09-21 사용자 지적 — 카드가 많으면 컬럼이 페이지 전체 높이만큼 늘어나서, 가로
  // 스크롤바가 페이지 맨 아래로 밀려나 손이 안 닿는 문제가 있었다. 컬럼 자체를 세로로
  // 고정 높이+내부 스크롤로 바꾸고(제목·설명은 위에 고정), 바깥(가로) 스크롤 영역도
  // 고정 높이를 줘서 상하좌우 스크롤이 항상 같은 화면 안에서 끝나게 한다.
  return (
    <Stack sx={{ minWidth: 320, maxWidth: 320, flexShrink: 0, height: "100%" }}>
      <Box sx={{ pb: 1, flexShrink: 0 }}>
        <Typography variant="subtitle1" fontWeight={700}>
          {title} ({items.length}건)
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
          {description}
        </Typography>
      </Box>
      <Stack spacing={1.5} sx={{ overflowY: "auto", flex: 1, pr: 0.5 }}>
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

// 관심공고 추천이 규칙(키워드) 매칭 하나뿐이라 "관계없는 것들이 섞인다"는 지적에, 다른
// 신호(코사인 유사도 등)를 나란히 계산해 비교해보는 페이지(2026-09-16, 의사결정_로그
// 157/158번 후속). 아직 규칙 매칭을 대체하지 않는다 — 눈으로 먼저 비교해보기 위함.
// 2026-09-21 — 신호를 "한꺼번에 다 넣지 않고 껐다 켰다 하며 비교"하고 싶다는 요청으로
// 고정 3열(규칙/코사인-제목/코사인-첨부)에서 백엔드가 내려주는 이름별 프로필 목록을 그대로
// N열로 렌더링하는 구조로 일반화했다(의사결정_로그 192번, PROFILE_PRESETS 참고). 코사인
// 계산이 모델 첫 로딩 시 1분 가까이 걸릴 수 있어(관측됨), 고객 선택만으로 자동 실행하지
// 않고 "매칭 시작" 버튼을 눌러야 계산하도록 바꿨다(사용자 지시).
export function MatchingComparisonPage() {
  const customersQuery = useQuery({ queryKey: ["customers"], queryFn: fetchCustomers });
  const [customerId, setCustomerId] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  function scrollByColumns(direction: 1 | -1) {
    // 2026-09-21 — 가로 스크롤이 있다는 게 안 보인다는 지적(마우스 휠/트랙패드로만 넘어가서
    // 티가 안 남) — 컬럼 폭(320)+간격(24) 두 칸만큼 화살표 버튼으로 넘길 수 있게 한다.
    scrollRef.current?.scrollBy({ left: direction * (320 + 24) * 2, behavior: "smooth" });
  }

  useEffect(() => {
    if (customerId === null && customersQuery.data && customersQuery.data.length > 0) {
      setCustomerId(customersQuery.data[0].id);
    }
  }, [customerId, customersQuery.data]);

  const compareQuery = useQuery({
    queryKey: ["interest-matches-compare", customerId],
    queryFn: () => fetchInterestMatchesCompare(customerId!),
    enabled: false, // 자동 실행 안 함 — "매칭 시작" 버튼을 눌러야 refetch()로 계산
    retry: false,
  });

  const profiles = compareQuery.data?.profiles ?? [];
  // 프로필별 id 집합 — "다른 프로필에도 나왔는지" 강조 표시에 쓴다(프로필 수가 3개→N개로
  // 늘어도 로직은 동일: 자기 자신을 뺀 나머지 전부의 합집합과 비교).
  const idsByProfile = new Map(profiles.map((p) => [p.key, new Set(p.matches.map((m) => m.id))]));

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h2">매칭 방식 비교</Typography>
        <Typography variant="body2" color="text.secondary">
          규칙(키워드) 매칭에 여러 신호(사업유형·코사인 유사도·sLLM confidence·A3 판정·전략
          열람)를 하나씩 얹은 결과가 같은 고객에게 얼마나 다르게 추천하는지 비교합니다.
          초록 테두리는 다른 조합에서도 나온 공고입니다.
        </Typography>
      </Box>

      <Stack direction="row" spacing={2} alignItems="center">
        <TextField
          select
          size="small"
          label="고객"
          value={customerId ?? ""}
          onChange={(e) => setCustomerId(Number(e.target.value))}
          sx={{ maxWidth: 320 }}
        >
          {(customersQuery.data ?? []).map((c) => (
            <MenuItem key={c.id} value={c.id}>
              {c.name}
            </MenuItem>
          ))}
        </TextField>
        <Button
          variant="contained"
          disabled={customerId === null || compareQuery.isFetching}
          onClick={() => compareQuery.refetch()}
        >
          매칭 시작
        </Button>
      </Stack>

      {compareQuery.isFetching && (
        <Stack direction="row" spacing={1.5} alignItems="center" sx={{ py: 2 }}>
          <CircularProgress size={20} />
          <Typography variant="body2" color="text.secondary">
            비교 결과 계산 중... (코사인 유사도 모델이 이번 서버 재시작 후 처음 쓰이는
            경우 1분 가까이 걸릴 수 있습니다 — 이후 요청부터는 훨씬 빨라집니다)
          </Typography>
        </Stack>
      )}

      {compareQuery.isError && (
        <Alert severity="error">{apiErrorMessage(compareQuery.error, "비교 결과를 불러오지 못했습니다.")}</Alert>
      )}

      {profiles.length > 0 && (
        // 2026-09-21 사용자 지시 — 여러 프로필을 가로로 나열(그리드로 줄바꿈하지 않음),
        // 컬럼 폭 고정 + 가로 스크롤. 스크롤 자체가 잘 안 보인다는 지적에 화살표 버튼과
        // 항상 보이는 스크롤바를 추가했다.
        <Box sx={{ position: "relative" }}>
          <IconButton
            aria-label="왼쪽으로 스크롤"
            onClick={() => scrollByColumns(-1)}
            sx={{
              position: "absolute", left: -8, top: "50%", transform: "translateY(-50%)", zIndex: 1,
              bgcolor: "background.paper", boxShadow: 2, "&:hover": { bgcolor: "background.paper" },
            }}
          >
            <ChevronLeftIcon />
          </IconButton>
          <Box
            ref={scrollRef}
            sx={{
              display: "flex",
              gap: 3,
              overflowX: "auto",
              // 2026-09-21 사용자 지적 — 카드가 많은 컬럼 때문에 이 영역이 페이지 전체
              // 높이만큼 늘어나면 가로 스크롤바가 화면 맨 아래로 밀려 손이 안 닿는다.
              // 높이를 화면 안으로 고정하고(컬럼마다 세로 스크롤은 MatchColumn 내부에서
              // 처리), 상하좌우 스크롤이 전부 이 박스 안에서 끝나게 한다.
              height: "calc(100vh - 320px)",
              minHeight: 400,
              pb: 1,
              px: 5,
              scrollbarWidth: "auto", // 파이어폭스 — 얇게 숨기지 않고 항상 보이게
              "&::-webkit-scrollbar": { height: 10 },
              "&::-webkit-scrollbar-thumb": { backgroundColor: "#9e9e9e", borderRadius: 5 },
            }}
          >
            {profiles.map((p) => {
              const otherIds = new Set(
                profiles.filter((other) => other.key !== p.key).flatMap((other) => [...(idsByProfile.get(other.key) ?? [])])
              );
              return (
                <MatchColumn
                  key={p.key}
                  title={p.label}
                  description={p.description}
                  items={p.matches}
                  otherIds={otherIds}
                  emptyHint="결과가 없습니다."
                />
              );
            })}
          </Box>
          <IconButton
            aria-label="오른쪽으로 스크롤"
            onClick={() => scrollByColumns(1)}
            sx={{
              position: "absolute", right: -8, top: "50%", transform: "translateY(-50%)", zIndex: 1,
              bgcolor: "background.paper", boxShadow: 2, "&:hover": { bgcolor: "background.paper" },
            }}
          >
            <ChevronRightIcon />
          </IconButton>
        </Box>
      )}
    </Stack>
  );
}
