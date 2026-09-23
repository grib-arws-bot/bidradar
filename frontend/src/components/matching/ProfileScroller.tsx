import ChevronLeftIcon from "@mui/icons-material/ChevronLeftOutlined";
import ChevronRightIcon from "@mui/icons-material/ChevronRightOutlined";
import { Box, IconButton } from "@mui/material";
import { useRef } from "react";

import type { MatchProfile } from "@/api/customerInterests";

import { MatchColumn } from "./MatchDisplay";

// 여러 프로필(신호 조합)을 가로로 나열하고 좌우 화살표+스크롤을 제공하는 공통 컨테이너
// (2026-09-21, 의사결정_로그 198번 — MatchingComparisonPage.tsx와 "전체 신호" 결합방식
// 비교 팝업이 공유). 컬럼 폭 고정 + 가로 스크롤, 화살표 버튼, 항상 보이는 스크롤바까지
// 전부 여기 있다.
//
// height는 호출부가 넘긴다. 2026-09-23 사용자 지시로 기본값을 "auto"로 바꿨다 — 컬럼별
// 세로 스크롤을 없애고(MatchDisplay.tsx의 MatchColumn 참고) 페이지 전체가 함께 스크롤
//되게 하려면, 이 컨테이너가 스스로 높이를 고정해 세로를 잘라내면 안 되기 때문이다(페이지
// 쪽 호출부는 height를 아예 안 넘긴다). 팝업(Dialog)은 뷰포트를 벗어날 수 없어 여전히
// 고정값("70vh")을 넘겨 내부 스크롤을 쓴다 — 가로 스크롤(overflowX)만 공통.
export function ProfileScroller({
  profiles,
  emptyHint = "결과가 없습니다.",
  height = "auto",
}: {
  profiles: MatchProfile[];
  emptyHint?: string;
  height?: string | number;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  function scrollByColumns(direction: 1 | -1) {
    scrollRef.current?.scrollBy({ left: direction * (320 + 24) * 2, behavior: "smooth" });
  }

  if (profiles.length === 0) return null;

  const idsByProfile = new Map(profiles.map((p) => [p.key, new Set(p.matches.map((m) => m.id))]));

  return (
    <Box sx={{ position: "relative", height }}>
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
          height: "100%",
          pb: 1,
          px: 5,
          scrollbarWidth: "auto",
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
              emptyHint={emptyHint}
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
  );
}
