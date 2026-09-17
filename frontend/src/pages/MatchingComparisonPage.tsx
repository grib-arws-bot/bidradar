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
  const scoreLabel = item.score !== undefined ? `규칙 ${item.score}점` : `유사도 ${item.cosine_score}점`;
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
        <Chip label={scoreLabel} size="small" color={bothMatched ? "success" : "default"} sx={{ flexShrink: 0 }} />
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

// 관심공고 추천이 규칙(키워드) 매칭 하나뿐이라 "관계없는 것들이 섞인다"는 지적에, 코사인
// 유사도 매칭을 나란히 계산해 비교해보는 페이지(2026-09-16, 의사결정_로그 157/158번 후속).
// 아직 규칙 매칭을 대체하지 않는다 — 눈으로 먼저 비교해보기 위함. 2026-09-17 — 규칙 매칭과
// 코사인(제목만)의 일치율이 20건 중 2~3건으로 너무 낮다는 지적에, 규칙 매칭은 이미 A1 첨부
// 텍스트로 재채점한다는 걸 확인하고 코사인(첨부 포함)을 추가해 3방향 비교로 확장했다. 또한
// 코사인 계산이 모델 첫 로딩 시 1분 가까이 걸릴 수 있어(관측됨), 고객 선택만으로 자동 실행
// 하지 않고 "매칭 시작" 버튼을 눌러야 계산하도록 바꿨다(사용자 지시).
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

  const ruleIds = new Set((compareQuery.data?.rule_based ?? []).map((m) => m.id));
  const cosineIds = new Set((compareQuery.data?.cosine ?? []).map((m) => m.id));
  const cosineAttachmentIds = new Set((compareQuery.data?.cosine_attachment ?? []).map((m) => m.id));

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h2">매칭 방식 비교</Typography>
        <Typography variant="body2" color="text.secondary">
          규칙(키워드) 매칭·코사인 유사도(제목만)·코사인 유사도(첨부 포함)가 같은 고객에게
          얼마나 다르게 추천하는지 비교합니다. 초록 테두리는 다른 방식에서도 나온 공고입니다.
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

      {compareQuery.data && compareQuery.data.pending_embeddings > 0 && (
        <Alert severity="info">
          아직 임베딩(제목) 계산이 안 된 공고 {compareQuery.data.pending_embeddings}건이 있어
          코사인(제목만) 결과에서 제외됐습니다 — 배치가 10분마다 자동으로 채웁니다.
        </Alert>
      )}

      {compareQuery.data && compareQuery.data.pending_embeddings_attachment > 0 && (
        <Alert severity="info">
          아직 임베딩(첨부 포함) 계산이 안 된 공고 {compareQuery.data.pending_embeddings_attachment}건이
          있어 코사인(첨부 포함) 결과에서 제외됐습니다 — 배치가 10분마다 자동으로 채웁니다.
        </Alert>
      )}

      {compareQuery.data && (
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr 1fr" }, gap: 3 }}>
          <MatchColumn
            title="규칙 매칭"
            items={compareQuery.data.rule_based}
            otherIds={new Set([...cosineIds, ...cosineAttachmentIds])}
            emptyHint="규칙 매칭 결과가 없습니다."
          />
          <MatchColumn
            title="코사인 유사도(제목만)"
            items={compareQuery.data.cosine}
            otherIds={new Set([...ruleIds, ...cosineAttachmentIds])}
            emptyHint="코사인 매칭 결과가 없습니다 — 공고 임베딩이 아직 없을 수 있습니다."
          />
          <MatchColumn
            title="코사인 유사도(첨부 포함)"
            items={compareQuery.data.cosine_attachment}
            otherIds={new Set([...ruleIds, ...cosineIds])}
            emptyHint="코사인 매칭 결과가 없습니다 — 첨부 임베딩이 아직 없을 수 있습니다."
          />
        </Box>
      )}
    </Stack>
  );
}
