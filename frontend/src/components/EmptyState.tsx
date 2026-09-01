import { Button, Stack, Typography } from "@mui/material";

// S1 빈 상태(구현스펙 06절). "내 관심"·"미처리" 탭이 빠지면서(2026-09-01 공고탐색 탭
// 재구성) 그 탭 전용 빈 상태(no-interest-profile/no-interest-match/no-untriaged)는
// 도달 불가능해져 정리함 — 필요해지면 탭을 되살릴 때 같이 복원.
export type EmptyStateVariant = "no-search-result" | "no-filter-result";

const COPY: Record<EmptyStateVariant, { title: string; description: string; actionLabel?: string }> = {
  "no-search-result": {
    title: "검색 결과가 없습니다",
    description: "검색어 철자를 확인하거나, 검색어를 줄여보세요.",
    actionLabel: "검색어 지우기",
  },
  "no-filter-result": {
    title: "이 조건에 맞는 공고가 없습니다",
    description: "적용된 필터를 줄이면 더 많은 결과를 볼 수 있습니다.",
    actionLabel: "필터 초기화",
  },
};

export function EmptyState({
  variant,
  onAction,
}: {
  variant: EmptyStateVariant;
  onAction?: () => void;
}) {
  const copy = COPY[variant];
  return (
    <Stack spacing={1.5} sx={{ py: 8, alignItems: "center", textAlign: "center" }}>
      <Typography variant="h3">{copy.title}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 420 }}>
        {copy.description}
      </Typography>
      {copy.actionLabel && onAction && (
        <Button variant="outlined" size="small" onClick={onAction} sx={{ mt: 1 }}>
          {copy.actionLabel}
        </Button>
      )}
    </Stack>
  );
}
