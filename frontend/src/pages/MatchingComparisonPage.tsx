import { Box, Button, CircularProgress, MenuItem, Stack, TextField, Typography, Alert } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchCustomers, fetchInterestMatchesCompare } from "@/api/customerInterests";
import { AllSignalVariantsDialog } from "@/components/matching/AllSignalVariantsDialog";
import { ProfileScroller } from "@/components/matching/ProfileScroller";
import { apiErrorMessage } from "@/utils/errors";

// 관심공고 추천이 규칙(키워드) 매칭 하나뿐이라 "관계없는 것들이 섞인다"는 지적에, 다른
// 신호(코사인 유사도 등)를 나란히 계산해 비교해보는 페이지(2026-09-16, 의사결정_로그
// 157/158번 후속). 아직 규칙 매칭을 대체하지 않는다 — 눈으로 먼저 비교해보기 위함.
// 2026-09-21 — 신호를 "한꺼번에 다 넣지 않고 껐다 켰다 하며 비교"하고 싶다는 요청으로
// 고정 3열(규칙/코사인-제목/코사인-첨부)에서 백엔드가 내려주는 이름별 프로필 목록을 그대로
// N열로 렌더링하는 구조로 일반화했다(의사결정_로그 192번, PROFILE_PRESETS 참고). 같은 날
// 후속 지시로 "전체 신호"(다섯 신호를 한꺼번에 노이즈-OR로 결합)를 이 메인 화면에서 빼고
// 결합 방식 자체를 실험하는 별도 팝업(AllSignalVariantsDialog)으로 옮겼다(198번) — 노이즈-OR
// 포화 문제로 다른 프로필과 결과가 너무 달라 보였기 때문. 카드/컬럼 렌더링은
// components/matching/(MatchDisplay·ProfileScroller)로 분리해 팝업과 공유한다.
export function MatchingComparisonPage() {
  const customersQuery = useQuery({ queryKey: ["customers"], queryFn: fetchCustomers });
  const [customerId, setCustomerId] = useState<number | null>(null);
  const [variantsDialogOpen, setVariantsDialogOpen] = useState(false);

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

  return (
    // 2026-09-21 재수정 — 가로 스크롤 영역 높이를 `calc(100vh - 320px)`로 대충 고정했더니
    // 버튼 하나 늘어난 것만으로 헤더 높이가 바뀌어 계산이 어긋나 스크롤바 밑에 여백이
    // 생겼다. 매직 넘버 대신 flexbox로 "화면에서 남는 공간을 그대로 채우기"로 바꾼다 —
    // DashboardLayout의 <main>이 p:4(위아래 32px씩=64px)라 그만큼만 빼면 된다.
    <Stack spacing={3} sx={{ height: "calc(100vh - 64px)" }}>
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
        <Button variant="outlined" disabled={customerId === null} onClick={() => setVariantsDialogOpen(true)}>
          "전체 신호" 결합 방식 비교
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

      {/* flex:1 + minHeight:0 — 위 헤더가 차지하는 만큼을 자동으로 빼고 나머지를 이
          박스가 다 차지한다(minHeight:0 없으면 flex 기본값 때문에 overflow가 안 먹혀
          카드가 찌그러진다 — MatchColumn과 같은 함정). */}
      <Box sx={{ flex: 1, minHeight: 0 }}>
        <ProfileScroller profiles={profiles} />
      </Box>

      <AllSignalVariantsDialog
        customerId={customerId}
        open={variantsDialogOpen}
        onClose={() => setVariantsDialogOpen(false)}
      />
    </Stack>
  );
}
