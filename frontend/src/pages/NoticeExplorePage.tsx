import ArrowForwardIcon from "@mui/icons-material/ArrowForwardOutlined";
import GridViewOutlinedIcon from "@mui/icons-material/GridViewOutlined";
import RefreshIcon from "@mui/icons-material/RefreshOutlined";
import ViewListOutlinedIcon from "@mui/icons-material/ViewListOutlined";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Pagination,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  fetchFilterOptions,
  fetchNoticeCounts,
  fetchNotices,
  rescanNoticeDedup,
  type NoticeItem,
  type NoticeTab,
} from "@/api/notices";
import { EmptyState } from "@/components/EmptyState";
import { NoticeCard } from "@/components/NoticeCard";
import { EMPTY_FILTERS, NoticeFilterBar, type NoticeFilterValues } from "@/components/NoticeFilterBar";
import { NoticeExcludeWordsBox } from "@/components/NoticeExcludeWordsBox";
import { apiErrorMessage } from "@/utils/errors";

// 탭(2026-09-03 재구성, 2번째) — stage(어느 소스에서 왔는가) 기준 2분류 대신 공고 생명주기
// (입찰미정→입찰예정→입찰접수→입찰마감) 기준으로 바꿨다. "전체"는 그대로 두고, 나머지 4개는
// 화살표로 흐름이 보이게 렌더링한다(아래 STATUS_TABS, JSX). 기본값은 "입찰접수"(지금 바로
// 참여 가능한 것) — 관심주제·발주기관·수집단계는 탭이 아니라 필터바의 다중선택으로.
const STATUS_TABS: { value: NoticeTab; label: string }[] = [
  { value: "unscheduled", label: "입찰미정" },
  { value: "upcoming", label: "입찰예정" },
  { value: "in_progress", label: "입찰접수" },
  { value: "closed", label: "입찰마감" },
];
const DEFAULT_TAB: NoticeTab = "in_progress";

type CardView = "list" | "grid";
const CARD_VIEW_STORAGE_KEY = "bidradar:notice-card-view";

function loadCardView(): CardView {
  try {
    const saved = localStorage.getItem(CARD_VIEW_STORAGE_KEY);
    return saved === "grid" ? "grid" : "list";
  } catch {
    return "list";
  }
}

// 2026-09-08 사용자 지시 — 이 순서·구성으로 확정(공고일 최신순이 기본).
const SORTS = [
  { value: "notice_date_desc", label: "공고일 최신순" },
  { value: "open_desc", label: "게시일 최신순" },
  { value: "close_asc", label: "마감임박순" },
  { value: "priority", label: "관심도순" },
  { value: "price_desc", label: "추정가격 높은순" },
];

function paramsToFilters(sp: URLSearchParams): NoticeFilterValues {
  return {
    domain: sp.getAll("domain[]").map(Number),
    org: sp.getAll("org[]").map(Number),
    org_category: sp.getAll("org_category[]"),
    source: sp.getAll("source[]").map(Number),
    region: sp.getAll("region[]"),
    stage: sp.getAll("stage[]"),
    biz_type: sp.getAll("biz_type[]"),
    work_type: sp.getAll("work_type[]"),
    price_min: sp.get("price_min") ?? "",
    price_max: sp.get("price_max") ?? "",
    close_in: sp.get("close_in") ?? "",
    status: sp.get("status") ?? "",
    qualified: sp.get("qualified") ?? "",
    exclude_group: sp.get("exclude_group") === "true",
    exclude_extra: sp.getAll("exclude_extra[]"),
  };
}

function buildQuery(sp: URLSearchParams): URLSearchParams {
  // 백엔드에 그대로 전달할 쿼리 — page/size 기본값까지 명시해서 URL만 봐도 전체 상태가 보이게 함.
  const out = new URLSearchParams(sp);
  if (!out.get("tab")) out.set("tab", DEFAULT_TAB);
  // 기본 정렬은 공고일 최신순(2026-09-08 사용자 지시, 백엔드 NoticeFilters.sort 기본값과 동일).
  if (!out.get("sort")) out.set("sort", "notice_date_desc");
  if (!out.get("page")) out.set("page", "1");
  // 3의 배수로(2026-09-07 사용자 지시) — 3열 그리드 보기에서 마지막 줄이 빈 칸 없이 꽉 차게.
  if (!out.get("size")) out.set("size", "21");
  return out;
}

export function NoticeExplorePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchInput, setSearchInput] = useState(searchParams.get("q") ?? "");
  // 보기 스타일(가로형/세로형, 2026-09-05) — 사용자 개인 취향이라 서버에 안 남기고 브라우저에만
  // 저장한다.
  const [cardView, setCardView] = useState<CardView>(loadCardView);
  const [dedupDialogOpen, setDedupDialogOpen] = useState(false);
  const queryClient = useQueryClient();

  function changeCardView(next: CardView | null) {
    if (!next) return; // ToggleButtonGroup은 이미 눌린 버튼을 다시 누르면 null을 준다 — 무시.
    setCardView(next);
    try {
      localStorage.setItem(CARD_VIEW_STORAGE_KEY, next);
    } catch {
      // 프라이빗 브라우징 등에서 저장 실패해도 이번 세션 안에서는 정상 동작해야 하므로 무시.
    }
  }

  const tab = (searchParams.get("tab") as NoticeTab) || DEFAULT_TAB;
  const sort = searchParams.get("sort") || "notice_date_desc";
  const page = Number(searchParams.get("page") ?? "1");
  const q = searchParams.get("q") ?? "";
  const filters = paramsToFilters(searchParams);

  // 검색 300ms 디바운스 — 입력 중엔 URL을 안 건드리다가, 멈추면 그때 반영(그 시점에 API 호출).
  useEffect(() => {
    const handle = setTimeout(() => {
      if (searchInput === (searchParams.get("q") ?? "")) return;
      updateParams({ q: searchInput || null, page: null });
    }, 300);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  function updateParams(patch: Record<string, string | string[] | null>) {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(patch)) {
      next.delete(key);
      if (value === null) continue;
      if (Array.isArray(value)) {
        value.forEach((v) => next.append(key, v));
      } else if (value !== "") {
        next.set(key, value);
      }
    }
    setSearchParams(next, { replace: false });
  }

  function handleFiltersChange(next: NoticeFilterValues) {
    updateParams({
      "domain[]": next.domain.map(String),
      "org[]": next.org.map(String),
      "org_category[]": next.org_category,
      "source[]": next.source.map(String),
      "region[]": next.region,
      "stage[]": next.stage,
      "biz_type[]": next.biz_type,
      "work_type[]": next.work_type,
      price_min: next.price_min || null,
      price_max: next.price_max || null,
      close_in: next.close_in || null,
      status: next.status || null,
      qualified: next.qualified || null,
      exclude_group: next.exclude_group ? "true" : null,
      "exclude_extra[]": next.exclude_extra,
      page: null,
    });
  }

  const filterOptionsQuery = useQuery({ queryKey: ["filter-options"], queryFn: fetchFilterOptions });
  const countsQuery = useQuery({ queryKey: ["notice-counts"], queryFn: fetchNoticeCounts });

  // 동일 발주기관·동일 사업명이 발주계획/사전규격/입찰공고 단계에 중복 등장하는 문제 정리
  // (2026-09-06) — 관리자가 눌러서 실행, 자동 실행 아님(S8 원칙 3과 같은 이유).
  const dedupMutation = useMutation({
    mutationFn: rescanNoticeDedup,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notices"] });
      queryClient.invalidateQueries({ queryKey: ["notice-counts"] });
    },
  });

  function openDedupDialog() {
    dedupMutation.reset();
    setDedupDialogOpen(true);
  }

  const query = buildQuery(searchParams);
  const listQuery = useQuery({
    queryKey: ["notices", query.toString()],
    queryFn: () => fetchNotices(query),
    placeholderData: (prev) => prev,
  });

  const total = listQuery.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / 20));

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h2">공고 탐색</Typography>
      </Box>

      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" useFlexGap spacing={2}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Chip
            label={countsQuery.data ? `전체 (${countsQuery.data.all})` : "전체"}
            onClick={() => updateParams({ tab: "all", page: null })}
            color={tab === "all" ? "primary" : "default"}
            variant={tab === "all" ? "filled" : "outlined"}
          />
          <Box sx={{ width: "1px", height: 20, bgcolor: "divider", mx: 0.5 }} />
          {STATUS_TABS.map((t, i) => (
            <Stack key={t.value} direction="row" alignItems="center" spacing={1}>
              {i > 0 && <ArrowForwardIcon sx={{ fontSize: 16, color: "text.disabled" }} />}
              <Chip
                label={countsQuery.data ? `${t.label} (${countsQuery.data[t.value]})` : t.label}
                onClick={() => updateParams({ tab: t.value, page: null })}
                color={tab === t.value ? "primary" : "default"}
                variant={tab === t.value ? "filled" : "outlined"}
              />
            </Stack>
          ))}
        </Stack>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <ToggleButtonGroup size="small" exclusive value={cardView} onChange={(_, next) => changeCardView(next)}>
            <ToggleButton value="list" aria-label="가로형 보기">
              <Tooltip title="가로형 — 한 줄에 하나씩">
                <ViewListOutlinedIcon fontSize="small" />
              </Tooltip>
            </ToggleButton>
            <ToggleButton value="grid" aria-label="세로형 보기">
              <Tooltip title="세로형 — 한 줄에 3개씩">
                <GridViewOutlinedIcon fontSize="small" />
              </Tooltip>
            </ToggleButton>
          </ToggleButtonGroup>
          <TextField
            select
            size="small"
            label="정렬"
            sx={{ width: 180 }}
            value={sort}
            onChange={(e) => updateParams({ sort: e.target.value, page: null })}
          >
            {SORTS.map((s) => (
              <MenuItem key={s.value} value={s.value}>
                {s.label}
              </MenuItem>
            ))}
          </TextField>
          <Button size="small" variant="outlined" startIcon={<RefreshIcon />} onClick={openDedupDialog}>
            중복 공고 정리
          </Button>
        </Stack>
      </Stack>

      {/* 제외 키워드(2026-09-13 사용자 지시) — 별도 관리 화면 대신 정렬 바로 아래 인라인
          박스로 통합, 그룹 추가·삭제·적용/즉석 단어까지 여기서 전부 처리 */}
      <NoticeExcludeWordsBox values={filters} onChange={handleFiltersChange} />

      {/* 검색+필터링을 합쳐 실제로 몇 건이 나오는지 검색창 바로 옆에(2026-09-05 요청, "이
          갯수는 검색 및 필터링에 의한 항목 갯수") */}
      <Stack direction="row" spacing={1.5} alignItems="center">
        <TextField
          placeholder="공고명으로 검색"
          size="small"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          sx={{ maxWidth: 420 }}
        />
        <Typography variant="body2" color="text.secondary" className="tnum" sx={{ fontWeight: 700 }}>
          {total.toLocaleString("ko-KR")}건
        </Typography>
      </Stack>

      <NoticeFilterBar options={filterOptionsQuery.data} values={filters} onChange={handleFiltersChange} />

      <NoticeListBody
        view={cardView}
        loading={listQuery.isLoading}
        items={listQuery.data?.items ?? []}
        q={q}
        onClearSearch={() => {
          setSearchInput("");
          updateParams({ q: null, page: null });
        }}
        onClearFilters={() => handleFiltersChange(EMPTY_FILTERS)}
      />

      {total > 0 && (
        <Stack alignItems="center">
          <Pagination
            count={pageCount}
            page={page}
            onChange={(_, value) => updateParams({ page: String(value) })}
          />
        </Stack>
      )}

      <Dialog open={dedupDialogOpen} onClose={() => setDedupDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>중복 공고 정리</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            동일 발주기관·동일 사업명이 발주계획/사전규격/입찰공고 단계에 걸쳐 중복 수집된 경우,
            가장 최근에 공고된 건만 남기고 이전 단계는 목록·통계에서 숨깁니다(삭제하지는 않음).
          </Alert>
          {dedupMutation.isSuccess && (
            <Alert severity="success">
              중복 그룹 {dedupMutation.data.groups_with_duplicates}건을 찾아 공고{" "}
              {dedupMutation.data.notices_updated}건의 상태를 갱신했습니다.
            </Alert>
          )}
          {dedupMutation.isError && (
            <Alert severity="error">{apiErrorMessage(dedupMutation.error, "중복 공고 정리에 실패했습니다.")}</Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDedupDialogOpen(false)}>닫기</Button>
          <Button variant="contained" disabled={dedupMutation.isPending} onClick={() => dedupMutation.mutate()}>
            실행
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

function NoticeListBody({
  view,
  loading,
  items,
  q,
  onClearSearch,
  onClearFilters,
}: {
  view: CardView;
  loading: boolean;
  items: NoticeItem[];
  q: string;
  onClearSearch: () => void;
  onClearFilters: () => void;
}) {
  if (loading) {
    return (
      <Stack alignItems="center" sx={{ py: 8 }}>
        <CircularProgress />
      </Stack>
    );
  }

  if (items.length === 0) {
    if (q) return <EmptyState variant="no-search-result" onAction={onClearSearch} />;
    return <EmptyState variant="no-filter-result" onAction={onClearFilters} />;
  }

  const cards = items.map((notice) => (
    <NoticeCard key={notice.id} notice={notice} highlight={q} variant={view} />
  ));

  if (view === "grid") {
    return (
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", md: "repeat(3, 1fr)" },
          gap: 1.5,
          alignItems: "stretch",
        }}
      >
        {cards}
      </Box>
    );
  }

  return <Stack spacing={1.5}>{cards}</Stack>;
}
