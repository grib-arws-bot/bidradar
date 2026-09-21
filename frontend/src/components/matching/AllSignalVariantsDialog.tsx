import CloseIcon from "@mui/icons-material/CloseOutlined";
import { Alert, Box, CircularProgress, Dialog, DialogContent, DialogTitle, IconButton, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { fetchAllSignalVariantsCompare } from "@/api/customerInterests";
import { apiErrorMessage } from "@/utils/errors";

import { ProfileScroller } from "./ProfileScroller";

// "전체 신호" 결합 방식만 따로 실험하는 팝업(2026-09-21, 의사결정_로그 198번) — 메인
// 매칭 방식 비교 화면에서 "전체 신호"를 빼고, 노이즈-OR 포화 문제를 해결할 후보 결합
// 방식(현재/가중치완화/코사인최소값/가중평균) 4가지를 여기서 비교한다.
export function AllSignalVariantsDialog({
  customerId,
  open,
  onClose,
}: {
  customerId: number | null;
  open: boolean;
  onClose: () => void;
}) {
  const variantsQuery = useQuery({
    queryKey: ["interest-matches-compare-all-signal-variants", customerId],
    queryFn: () => fetchAllSignalVariantsCompare(customerId!),
    enabled: open && customerId !== null,
    retry: false,
  });

  const profiles = variantsQuery.data?.profiles ?? [];

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xl" fullWidth>
      <DialogTitle sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <Box>
          <Typography variant="h3">"전체 신호" 결합 방식 비교</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            다섯 신호(사업유형·코사인·sLLM·A3·전략열람)를 한꺼번에 결합할 때, 결합 방식에
            따라 결과가 얼마나 달라지는지 비교합니다. 노이즈-OR은 신호 하나만 강해도
            빠르게 포화되는 특성이 있어 대안 세 가지를 나란히 뒀습니다.
          </Typography>
        </Box>
        <IconButton onClick={onClose} aria-label="닫기">
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        {variantsQuery.isFetching && (
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ py: 2 }}>
            <CircularProgress size={20} />
            <Typography variant="body2" color="text.secondary">
              비교 결과 계산 중...
            </Typography>
          </Stack>
        )}
        {variantsQuery.isError && (
          <Alert severity="error">{apiErrorMessage(variantsQuery.error, "비교 결과를 불러오지 못했습니다.")}</Alert>
        )}
        {/* Dialog 안이라 페이지처럼 flex 조상 체인이 없다 — 뷰포트 기준 고정값을 그대로 쓴다. */}
        <ProfileScroller profiles={profiles} height="70vh" />
      </DialogContent>
    </Dialog>
  );
}
