import { Alert, Box, Button, Card, Chip, CircularProgress, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
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

// 요약 카드 하나 — 상세 카드(NoticeCard 등)보다 훨씬 압축해서 2열 비교가 한 화면에 들어오게
// 한다. bothMatched면 두 방식이 동의한 공고라 강조 표시(2026-09-16 사용자 지시 — "양쪽에 다
// 나오는 공고는 강조 표시").
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
    </Card>
  );
}

function MatchColumn({
  title,
  items,
  otherIds,
  emptyHint,
}: {
  title: string;
  items: MatchItem[];
  otherIds: Set<number>;
  emptyHint: string;
}) {
  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle1" fontWeight={700}>
        {title} ({items.length}건)
      </Typography>
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {emptyHint}
        </Typography>
      ) : (
        items.map((item) => <MatchCard key={item.id} item={item} bothMatched={otherIds.has(item.id)} />)
      )}
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
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", md: `repeat(${Math.min(profiles.length, 3)}, 1fr)` },
            gap: 3,
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
                items={p.matches}
                otherIds={otherIds}
                emptyHint="결과가 없습니다."
              />
            );
          })}
        </Box>
      )}
    </Stack>
  );
}
