import { Button, Stack, Typography } from "@mui/material";

// S1 빈 상태 5종(구현스펙 06절) — 각각 다른 문구·복구 버튼.
export type EmptyStateVariant =
  | "no-interest-profile"
  | "no-interest-match"
  | "no-search-result"
  | "no-untriaged"
  | "no-filter-result";

const COPY: Record<EmptyStateVariant, { title: string; description: string; actionLabel?: string }> = {
  "no-interest-profile": {
    title: "아직 관심 주제를 설정하지 않았습니다",
    description: "관심 주제를 설정하면 이 탭에 매칭되는 공고만 모아서 보여드립니다.",
    actionLabel: "관심 주제 설정하러 가기",
  },
  "no-interest-match": {
    title: "설정한 관심 주제에 매칭되는 공고가 없습니다",
    description: "관심 주제 범위를 넓히거나, '전체' 탭에서 직접 찾아보세요.",
    actionLabel: "전체 탭으로 보기",
  },
  "no-search-result": {
    title: "검색 결과가 없습니다",
    description: "검색어 철자를 확인하거나, 검색어를 줄여보세요.",
    actionLabel: "검색어 지우기",
  },
  "no-untriaged": {
    title: "미처리 공고가 없습니다",
    description: "오늘 확인해야 할 분류 검수 대상을 모두 처리했습니다.",
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
