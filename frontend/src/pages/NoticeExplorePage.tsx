import {
  Box,
  CircularProgress,
  MenuItem,
  Pagination,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { ClassificationAction } from "@/api/classification";
import { fetchFilterOptions, fetchNoticeCounts, fetchNotices, type FilterOptions, type NoticeItem, type NoticeTab } from "@/api/notices";
import { EmptyState } from "@/components/EmptyState";
import { NoticeCard } from "@/components/NoticeCard";
import { EMPTY_FILTERS, NoticeFilterBar, type NoticeFilterValues } from "@/components/NoticeFilterBar";

const TABS: { value: NoticeTab; label: string }[] = [
  { value: "mine", label: "내 관심" },
  { value: "all", label: "전체" },
  { value: "untriaged", label: "미처리" },
  { value: "assigned", label: "내 담당" },
];

const SORTS = [
  { value: "priority", label: "관심도순" },
  { value: "close_asc", label: "마감임박순" },
  { value: "open_desc", label: "게시일 최신순" },
  { value: "price_desc", label: "추정가격 높은순" },
  { value: "price_asc", label: "추정가격 낮은순" },
];

function paramsToFilters(sp: URLSearchParams): NoticeFilterValues {
  return {
    domain: sp.getAll("domain[]").map(Number),
    org: sp.getAll("org[]").map(Number),
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
  };
}

function buildQuery(sp: URLSearchParams): URLSearchParams {
  // 백엔드에 그대로 전달할 쿼리 — page/size 기본값까지 명시해서 URL만 봐도 전체 상태가 보이게 함.
  const out = new URLSearchParams(sp);
  if (!out.get("tab")) out.set("tab", "mine");
  if (!out.get("sort")) out.set("sort", "priority");
  if (!out.get("page")) out.set("page", "1");
  if (!out.get("size")) out.set("size", "20");
  return out;
}

export function NoticeExplorePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchInput, setSearchInput] = useState(searchParams.get("q") ?? "");
  // U5: 분류검수 액션은 "카드만 갱신" — 목록을 다시 안 부르고 이 로컬 맵만 바꾼다.
  const [classifiedMap, setClassifiedMap] = useState<Map<number, ClassificationAction>>(new Map());

  const tab = (searchParams.get("tab") as NoticeTab) || "mine";
  const sort = searchParams.get("sort") || "priority";
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
      page: null,
    });
  }

  const filterOptionsQuery = useQuery({ queryKey: ["filter-options"], queryFn: fetchFilterOptions });
  const countsQuery = useQuery({ queryKey: ["notice-counts"], queryFn: fetchNoticeCounts });

  const query = buildQuery(searchParams);
  const listQuery = useQuery({
    queryKey: ["notices", query.toString()],
    queryFn: () => fetchNotices(query),
    placeholderData: (prev) => prev,
  });

  const hasAnyFilter = useMemo(
    () =>
      Boolean(
        filters.domain.length ||
          filters.org.length ||
          filters.source.length ||
          filters.region.length ||
          filters.stage.length ||
          filters.price_min ||
          filters.price_max ||
          filters.close_in ||
          filters.status ||
          filters.qualified,
      ),
    [filters],
  );

  const total = listQuery.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / 20));

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h2">공고 탐색</Typography>
        <Typography variant="body2" color="text.secondary">
          사전규격 단계부터 — 이미 늦기 전에 봅니다.
        </Typography>
      </Box>

      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" useFlexGap>
        <Tabs value={tab} onChange={(_, value) => updateParams({ tab: value, page: null })}>
          {TABS.map((t) => (
            <Tab
              key={t.value}
              value={t.value}
              label={countsQuery.data ? `${t.label} (${countsQuery.data[t.value]})` : t.label}
            />
          ))}
        </Tabs>
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
      </Stack>

      <TextField
        placeholder="공고명으로 검색"
        size="small"
        value={searchInput}
        onChange={(e) => setSearchInput(e.target.value)}
        sx={{ maxWidth: 420 }}
      />

      <NoticeFilterBar options={filterOptionsQuery.data} values={filters} onChange={handleFiltersChange} />

      <NoticeListBody
        loading={listQuery.isLoading}
        items={listQuery.data?.items ?? []}
        q={q}
        tab={tab}
        hasAnyFilter={hasAnyFilter}
        topics={filterOptionsQuery.data?.topics ?? []}
        classifiedMap={classifiedMap}
        onClassified={(id, action) => setClassifiedMap((prev) => new Map(prev).set(id, action))}
        onClearSearch={() => {
          setSearchInput("");
          updateParams({ q: null, page: null });
        }}
        onClearFilters={() => handleFiltersChange(EMPTY_FILTERS)}
        onGoAllTab={() => updateParams({ tab: "all", page: null })}
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
    </Stack>
  );
}

function NoticeListBody({
  loading,
  items,
  q,
  tab,
  hasAnyFilter,
  topics,
  classifiedMap,
  onClassified,
  onClearSearch,
  onClearFilters,
  onGoAllTab,
}: {
  loading: boolean;
  items: NoticeItem[];
  q: string;
  tab: NoticeTab;
  hasAnyFilter: boolean;
  topics: FilterOptions["topics"];
  classifiedMap: Map<number, ClassificationAction>;
  onClassified: (noticeId: number, action: ClassificationAction) => void;
  onClearSearch: () => void;
  onClearFilters: () => void;
  onGoAllTab: () => void;
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
    if (hasAnyFilter) return <EmptyState variant="no-filter-result" onAction={onClearFilters} />;
    if (tab === "untriaged") return <EmptyState variant="no-untriaged" />;
    if (tab === "mine") return <EmptyState variant="no-interest-match" onAction={onGoAllTab} />;
    return <EmptyState variant="no-filter-result" onAction={onClearFilters} />;
  }

  return (
    <Stack spacing={1.5}>
      {items.map((notice) => (
        <NoticeCard
          key={notice.id}
          notice={notice}
          highlight={q}
          topics={topics}
          classifiedAs={classifiedMap.get(notice.id) ?? null}
          onClassified={onClassified}
        />
      ))}
    </Stack>
  );
}
