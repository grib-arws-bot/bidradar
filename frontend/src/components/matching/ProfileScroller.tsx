import ChevronLeftIcon from "@mui/icons-material/ChevronLeftOutlined";
import ChevronRightIcon from "@mui/icons-material/ChevronRightOutlined";
import { Box, IconButton } from "@mui/material";
import { useRef } from "react";

import type { MatchProfile } from "@/api/customerInterests";

import { MatchColumn } from "./MatchDisplay";

// 여러 프로필(신호 조합)을 가로로 나열하고 좌우 화살표+고정 높이 스크롤을 제공하는
// 공통 컨테이너(2026-09-21, 의사결정_로그 198번 — MatchingComparisonPage.tsx와 "전체 신호"
// 결합방식 비교 팝업이 공유). 컬럼 폭 고정 + 가로 스크롤, 화살표 버튼, 항상 보이는
// 스크롤바, 뷰포트 기준 고정 높이(197번 — 카드가 많아 페이지 전체 높이로 늘어나 스크롤바가
// 손에 안 닿던 문제 수정)까지 전부 여기 있다.
export function ProfileScroller({ profiles, emptyHint = "결과가 없습니다." }: { profiles: MatchProfile[]; emptyHint?: string }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  function scrollByColumns(direction: 1 | -1) {
    scrollRef.current?.scrollBy({ left: direction * (320 + 24) * 2, behavior: "smooth" });
  }

  if (profiles.length === 0) return null;

  const idsByProfile = new Map(profiles.map((p) => [p.key, new Set(p.matches.map((m) => m.id))]));

  return (
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
          height: "calc(100vh - 320px)",
          minHeight: 400,
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
