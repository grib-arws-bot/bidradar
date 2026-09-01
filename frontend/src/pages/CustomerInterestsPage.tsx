import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import {
  Autocomplete,
  Box,
  Button,
  Card,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";

import {
  deleteSavedSearch,
  fetchCustomers,
  fetchInterestProfile,
  fetchSavedSearches,
  previewInterestProfile,
  saveInterestProfile,
  type InterestDraft,
} from "@/api/customerInterests";
import { fetchFilterOptions } from "@/api/notices";
import { fetchReports, generateReport } from "@/api/reports";

const EMPTY_DRAFT: InterestDraft = {
  topic_ids: [],
  terms: [],
  followed_org_ids: [],
  price_min: null,
  price_max: null,
  regions: [],
};

export function CustomerInterestsPage() {
  const queryClient = useQueryClient();
  const customersQuery = useQuery({ queryKey: ["customers"], queryFn: fetchCustomers });
  const filterOptionsQuery = useQuery({ queryKey: ["filter-options"], queryFn: fetchFilterOptions });

  const [customerId, setCustomerId] = useState<number | null>(null);
  const [draft, setDraft] = useState<InterestDraft>(EMPTY_DRAFT);
  const [termInput, setTermInput] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (customerId === null && customersQuery.data && customersQuery.data.length > 0) {
      setCustomerId(customersQuery.data[0].id);
    }
  }, [customerId, customersQuery.data]);

  const profileQuery = useQuery({
    queryKey: ["interest-profile", customerId],
    queryFn: () => fetchInterestProfile(customerId!),
    enabled: customerId !== null,
  });

  useEffect(() => {
    if (profileQuery.data) {
      setDraft({
        topic_ids: profileQuery.data.topic_ids,
        terms: profileQuery.data.terms,
        followed_org_ids: profileQuery.data.followed_org_ids,
        price_min: profileQuery.data.price_min,
        price_max: profileQuery.data.price_max,
        regions: profileQuery.data.regions,
      });
      setSaved(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileQuery.data]);

  const savedSearchesQuery = useQuery({
    queryKey: ["saved-searches", customerId],
    queryFn: () => fetchSavedSearches(customerId!),
    enabled: customerId !== null,
  });

  // 프리셋 토글·키워드·기관 변경 시 저장 전에도 미리보기 즉시 갱신(S7 "동작") — 300ms 디바운스.
  const [debouncedDraft, setDebouncedDraft] = useState(draft);
  useEffect(() => {
    const handle = setTimeout(() => setDebouncedDraft(draft), 300);
    return () => clearTimeout(handle);
  }, [draft]);

  const previewQuery = useQuery({
    queryKey: ["interest-preview", customerId, debouncedDraft],
    queryFn: () => previewInterestProfile(customerId!, debouncedDraft),
    enabled: customerId !== null,
  });

  const saveMutation = useMutation({
    mutationFn: () => saveInterestProfile(customerId!, draft),
    onSuccess: () => {
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["interest-profile", customerId] });
    },
  });

  const deleteSearchMutation = useMutation({
    mutationFn: (searchId: number) => deleteSavedSearch(customerId!, searchId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["saved-searches", customerId] }),
  });

  const reportsQuery = useQuery({
    queryKey: ["reports", customerId],
    queryFn: () => fetchReports(customerId!),
    enabled: customerId !== null,
  });

  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  const generateReportMutation = useMutation({
    mutationFn: () => generateReport(customerId!),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: ["reports", customerId] });
      void navigator.clipboard?.writeText(`${window.location.origin}/r/${report.token}`);
      setCopiedToken(report.token);
    },
  });

  function update(patch: Partial<InterestDraft>) {
    setDraft((prev) => ({ ...prev, ...patch }));
    setSaved(false);
  }

  function addTerm() {
    const term = termInput.trim();
    if (!term || draft.terms.includes(term)) return;
    update({ terms: [...draft.terms, term] });
    setTermInput("");
  }

  const topics = profileQuery.data?.topics ?? [];
  const orgs = filterOptionsQuery.data?.orgs ?? [];
  const regions = filterOptionsQuery.data?.regions ?? [];

  return (
    <Stack spacing={3} sx={{ maxWidth: 960 }}>
      <Box>
        <Typography variant="h2">고객 관심 주제 관리</Typography>
        <Typography variant="body2" color="text.secondary">
          고객(그립 자신 포함)마다 관심 주제를 설정합니다 — Standard 뉴스레터의 실제 설정 진입점입니다.
        </Typography>
      </Box>

      <TextField
        select
        label="고객"
        sx={{ maxWidth: 320 }}
        value={customerId ?? ""}
        onChange={(e) => setCustomerId(Number(e.target.value))}
      >
        {(customersQuery.data ?? []).map((c) => (
          <MenuItem key={c.id} value={c.id}>
            {c.name} {c.plan_tier === "internal" ? "(그립 자신)" : `(${c.plan_tier})`}
          </MenuItem>
        ))}
      </TextField>

      {profileQuery.isLoading ? (
        <CircularProgress />
      ) : (
        <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
          <Card sx={{ p: 3, flex: 1.4 }}>
            <Stack spacing={3}>
              <Box>
                <Typography variant="h3" sx={{ mb: 1 }}>
                  관심 분야(대분류)
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {topics.map((t) => {
                    const active = draft.topic_ids.includes(t.id);
                    return (
                      <Chip
                        key={t.id}
                        label={t.name}
                        color={active ? "primary" : "default"}
                        variant={active ? "filled" : "outlined"}
                        onClick={() =>
                          update({
                            topic_ids: active
                              ? draft.topic_ids.filter((id) => id !== t.id)
                              : [...draft.topic_ids, t.id],
                          })
                        }
                      />
                    );
                  })}
                </Stack>
              </Box>

              <Box>
                <Typography variant="h3" sx={{ mb: 1 }}>
                  직접 키워드
                </Typography>
                <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
                  <TextField
                    size="small"
                    placeholder="키워드 입력 후 Enter"
                    value={termInput}
                    onChange={(e) => setTermInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && addTerm()}
                    fullWidth
                  />
                  <Button variant="outlined" onClick={addTerm}>
                    추가
                  </Button>
                </Stack>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {draft.terms.map((term) => {
                    const count = previewQuery.data?.term_counts[term] ?? 0;
                    return (
                      <Chip
                        key={term}
                        label={`${term} · 최근 30일 ${count}건`}
                        onDelete={() => update({ terms: draft.terms.filter((t) => t !== term) })}
                        sx={count === 0 ? { opacity: 0.5 } : undefined}
                      />
                    );
                  })}
                </Stack>
              </Box>

              <Box>
                <Typography variant="h3" sx={{ mb: 1 }}>
                  팔로우 기관
                </Typography>
                <Autocomplete
                  multiple
                  size="small"
                  options={orgs}
                  getOptionLabel={(o) => o.name}
                  isOptionEqualToValue={(a, b) => a.id === b.id}
                  value={orgs.filter((o) => draft.followed_org_ids.includes(o.id))}
                  onChange={(_, selected) => update({ followed_org_ids: selected.map((s) => s.id) })}
                  renderInput={(params) => <TextField {...params} placeholder="기관 선택" />}
                />
              </Box>

              <Stack direction="row" spacing={2}>
                <TextField
                  size="small"
                  label="추정가격 최소"
                  type="number"
                  value={draft.price_min ?? ""}
                  onChange={(e) => update({ price_min: e.target.value ? Number(e.target.value) : null })}
                  fullWidth
                />
                <TextField
                  size="small"
                  label="추정가격 최대"
                  type="number"
                  value={draft.price_max ?? ""}
                  onChange={(e) => update({ price_max: e.target.value ? Number(e.target.value) : null })}
                  fullWidth
                />
              </Stack>

              <Autocomplete
                multiple
                size="small"
                options={regions}
                value={draft.regions}
                onChange={(_, selected) => update({ regions: selected })}
                renderInput={(params) => <TextField {...params} label="지역" />}
              />

              <Stack direction="row" spacing={2} alignItems="center">
                <Button
                  variant="contained"
                  size="large"
                  disabled={saveMutation.isPending}
                  onClick={() => saveMutation.mutate()}
                >
                  저장
                </Button>
                {saved && (
                  <Typography variant="body2" color="success.main">
                    저장됐습니다.
                  </Typography>
                )}
              </Stack>
            </Stack>
          </Card>

          <Card sx={{ p: 3, flex: 1 }}>
            <Typography variant="h3" sx={{ mb: 1 }}>
              미리보기 (저장 전)
            </Typography>
            {previewQuery.isFetching ? (
              <CircularProgress size={20} />
            ) : (
              <>
                <Typography variant="body1" fontWeight={600} sx={{ mb: 1 }}>
                  {previewQuery.data?.count ?? 0}건 매칭
                </Typography>
                <Stack spacing={1}>
                  {(previewQuery.data?.samples ?? []).map((s) => (
                    <Box key={s.id} sx={{ p: 1, borderRadius: 1, bgcolor: "grey.100" }}>
                      <Typography variant="body2" noWrap>
                        {s.title}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {s.org_name} · 관심도 {s.score}
                      </Typography>
                    </Box>
                  ))}
                  {previewQuery.data && previewQuery.data.count === 0 && (
                    <Typography variant="body2" color="text.secondary">
                      조건에 맞는 공고가 없습니다.
                    </Typography>
                  )}
                </Stack>
              </>
            )}

            <Divider sx={{ my: 2 }} />

            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
              <Typography variant="h3">관심분야 리포트</Typography>
              <Button
                size="small"
                variant="outlined"
                disabled={generateReportMutation.isPending}
                onClick={() => generateReportMutation.mutate()}
              >
                지금 생성
              </Button>
            </Stack>
            {copiedToken && (
              <Typography variant="caption" color="success.main" sx={{ display: "block", mb: 1 }}>
                링크가 클립보드에 복사됐습니다: /r/{copiedToken}
              </Typography>
            )}
            <List dense disablePadding sx={{ mb: 2 }}>
              {(reportsQuery.data ?? []).map((r) => (
                <ListItem key={r.id} disableGutters>
                  <ListItemText
                    primary={`${new Date(r.generated_at).toLocaleDateString("ko-KR")} · ${r.summary.total}건`}
                    secondary={
                      <RouterLink to={`/r/${r.token}`} target="_blank" rel="noreferrer">
                        /r/{r.token} (조회 {r.view_count}회)
                      </RouterLink>
                    }
                  />
                </ListItem>
              ))}
              {(reportsQuery.data ?? []).length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  아직 생성한 리포트가 없습니다.
                </Typography>
              )}
            </List>

            <Divider sx={{ my: 2 }} />

            <Typography variant="h3" sx={{ mb: 1 }}>
              저장한 검색
            </Typography>
            <List dense disablePadding>
              {(savedSearchesQuery.data ?? []).map((s) => (
                <ListItem
                  key={s.id}
                  disableGutters
                  secondaryAction={
                    <IconButton size="small" onClick={() => deleteSearchMutation.mutate(s.id)}>
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  }
                >
                  <ListItemText primary={s.name} />
                </ListItem>
              ))}
              {(savedSearchesQuery.data ?? []).length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  저장한 검색이 없습니다.
                </Typography>
              )}
            </List>
          </Card>
        </Stack>
      )}
    </Stack>
  );
}
