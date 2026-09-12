import CloseIcon from "@mui/icons-material/Close";
import { Autocomplete, Chip, FormControlLabel, MenuItem, Stack, Switch, TextField, Tooltip } from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import type { FilterOptions } from "@/api/notices";
import { fetchNoticeExcludeWords } from "@/api/noticeExcludeWords";

export interface NoticeFilterValues {
  domain: number[];
  org: number[];
  // 발주기관 "분야"(2026-09-11) — 개별 기관(org)과 별개로 OR 결합된다. 예: 특정 기관 2곳을
  // org로 콕 집으면서 동시에 "교육" 분야 전체도 같이 볼 수 있다.
  org_category: string[];
  source: number[];
  region: string[];
  stage: string[];
  biz_type: string[];
  work_type: string[];
  price_min: string;
  price_max: string;
  close_in: string;
  status: string;
  qualified: string;
  // 제목 제외 키워드(2026-09-13) — exclude_group은 "제외 키워드" 관리 화면에 저장된 목록
  // 전체를 켜고 끄는 스위치, exclude_extra는 이 화면에서 그때그때 추가하는 단어(저장 안 됨).
  exclude_group: boolean;
  exclude_extra: string[];
}

export const EMPTY_FILTERS: NoticeFilterValues = {
  domain: [],
  org: [],
  org_category: [],
  source: [],
  region: [],
  stage: [],
  biz_type: [],
  work_type: [],
  price_min: "",
  price_max: "",
  close_in: "",
  status: "",
  qualified: "",
  exclude_group: false,
  exclude_extra: [],
};

interface Props {
  options: FilterOptions | undefined;
  values: NoticeFilterValues;
  onChange: (values: NoticeFilterValues) => void;
}

// "데이터 소스" 필터는 채널(공고기관) 단위로 선택하지만 실제 값은 개별 source_id 배열로
// 보관한다(백엔드가 이미 그 형태를 받음) — 그 채널의 source_ids가 전부 선택돼 있으면 그
// 채널이 "선택됨"으로 보인다.
function selectedChannels(
  channels: FilterOptions["channels"],
  sourceIds: number[],
): FilterOptions["channels"] {
  return channels.filter((c) => c.source_ids.every((id) => sourceIds.includes(id)));
}

// 필터 9종(구현스펙 04절): domain·org·source·price(min+max 합쳐 1종)·region·stage·close_in·status·qualified
export function NoticeFilterBar({ options, values, onChange }: Props) {
  const set = <K extends keyof NoticeFilterValues>(key: K, value: NoticeFilterValues[K]) =>
    onChange({ ...values, [key]: value });

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
        <Autocomplete
          multiple
          size="small"
          sx={{ minWidth: 200 }}
          options={options?.topics ?? []}
          getOptionLabel={(o) => o.name}
          value={(options?.topics ?? []).filter((t) => values.domain.includes(t.id))}
          onChange={(_, selected) => set("domain", selected.map((s) => s.id))}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => <TextField {...params} label="관심 분야" />}
        />
        <Autocomplete
          multiple
          size="small"
          sx={{ minWidth: 200 }}
          options={options?.orgs ?? []}
          getOptionLabel={(o) => o.name}
          value={(options?.orgs ?? []).filter((o) => values.org.includes(o.id))}
          onChange={(_, selected) => set("org", selected.map((s) => s.id))}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => <TextField {...params} label="발주기관" />}
        />
        <Autocomplete
          multiple
          size="small"
          sx={{ minWidth: 180 }}
          options={options?.org_categories ?? []}
          value={values.org_category}
          onChange={(_, selected) => set("org_category", selected)}
          renderInput={(params) => <TextField {...params} label="발주기관 분야" />}
        />
        <Autocomplete
          multiple
          size="small"
          sx={{ minWidth: 200 }}
          options={options?.channels ?? []}
          getOptionLabel={(c) => c.name}
          value={selectedChannels(options?.channels ?? [], values.source)}
          onChange={(_, selected) => set("source", selected.flatMap((c) => c.source_ids))}
          isOptionEqualToValue={(a, b) => a.name === b.name}
          renderInput={(params) => <TextField {...params} label="데이터 소스" />}
        />
        <Autocomplete
          multiple
          size="small"
          sx={{ minWidth: 160 }}
          options={options?.regions ?? []}
          value={values.region}
          onChange={(_, selected) => set("region", selected)}
          renderInput={(params) => <TextField {...params} label="지역" />}
        />
        <Autocomplete
          multiple
          size="small"
          sx={{ minWidth: 180 }}
          options={options?.stages ?? []}
          value={values.stage}
          onChange={(_, selected) => set("stage", selected)}
          renderInput={(params) => <TextField {...params} label="단계" />}
        />
        <Autocomplete
          multiple
          size="small"
          sx={{ minWidth: 160 }}
          options={options?.biz_types ?? []}
          value={values.biz_type}
          onChange={(_, selected) => set("biz_type", selected)}
          renderInput={(params) => <TextField {...params} label="업무구분" />}
        />
        <Autocomplete
          multiple
          size="small"
          sx={{ minWidth: 180 }}
          options={options?.work_types ?? []}
          value={values.work_type}
          onChange={(_, selected) => set("work_type", selected)}
          renderInput={(params) => <TextField {...params} label="사업유형(추정)" />}
        />
      </Stack>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
        <TextField
          size="small"
          label="추정가격 최소"
          type="number"
          sx={{ width: 160 }}
          value={values.price_min}
          onChange={(e) => set("price_min", e.target.value)}
        />
        <TextField
          size="small"
          label="추정가격 최대"
          type="number"
          sx={{ width: 160 }}
          value={values.price_max}
          onChange={(e) => set("price_max", e.target.value)}
        />
        <TextField
          select
          size="small"
          label="마감 임박"
          sx={{ width: 140 }}
          value={values.close_in}
          onChange={(e) => set("close_in", e.target.value)}
        >
          <MenuItem value="">전체</MenuItem>
          <MenuItem value="3">3일 이내</MenuItem>
          <MenuItem value="7">7일 이내</MenuItem>
          <MenuItem value="14">14일 이내</MenuItem>
          <MenuItem value="30">30일 이내</MenuItem>
        </TextField>
        <TextField
          select
          size="small"
          label="상태"
          sx={{ width: 120 }}
          value={values.status}
          onChange={(e) => set("status", e.target.value)}
        >
          <MenuItem value="">전체</MenuItem>
          <MenuItem value="open">진행중</MenuItem>
          <MenuItem value="closed">마감</MenuItem>
        </TextField>
        <TextField
          select
          size="small"
          label="자격 충족"
          sx={{ width: 140 }}
          value={values.qualified}
          onChange={(e) => set("qualified", e.target.value)}
        >
          <MenuItem value="">전체</MenuItem>
          <MenuItem value="true">충족</MenuItem>
          <MenuItem value="false">미충족</MenuItem>
        </TextField>
      </Stack>
      <ExcludeWordsRow values={values} onChange={onChange} />
      <AppliedChips options={options} values={values} onChange={onChange} />
    </Stack>
  );
}

// 제목 제외 키워드(2026-09-13) — "제외 키워드" 관리 화면(/admin/notice-exclude-words)에
// 저장된 목록을 스위치 하나로 켜고 끄고, 그 옆에서 이번 조회에만 쓸 단어를 즉석으로 더
// 추가할 수 있다(저장 안 됨, freeSolo 다중입력).
function ExcludeWordsRow({
  values,
  onChange,
}: {
  values: NoticeFilterValues;
  onChange: (values: NoticeFilterValues) => void;
}) {
  const { data: excludeWords } = useQuery({
    queryKey: ["notice-exclude-words"],
    queryFn: fetchNoticeExcludeWords,
  });
  const terms = excludeWords?.map((w) => w.term) ?? [];

  return (
    <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
      <Tooltip title={terms.length > 0 ? `저장된 단어: ${terms.join(", ")}` : "등록된 제외 단어가 없습니다"}>
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={values.exclude_group}
              onChange={(e) => onChange({ ...values, exclude_group: e.target.checked })}
            />
          }
          label={`제외 키워드 그룹 적용 (${terms.length}개)`}
        />
      </Tooltip>
      <Autocomplete
        multiple
        freeSolo
        size="small"
        sx={{ minWidth: 260 }}
        options={[]}
        value={values.exclude_extra}
        onChange={(_, selected) => onChange({ ...values, exclude_extra: selected as string[] })}
        renderInput={(params) => (
          <TextField {...params} label="이번 조회에만 제외할 단어(엔터로 추가)" />
        )}
      />
    </Stack>
  );
}

function AppliedChips({ options, values, onChange }: Props) {
  const chips: { key: string; label: string; onDelete: () => void }[] = [];

  values.domain.forEach((id) => {
    const name = options?.topics.find((t) => t.id === id)?.name ?? String(id);
    chips.push({
      key: `domain-${id}`,
      label: `분야: ${name}`,
      onDelete: () => onChange({ ...values, domain: values.domain.filter((v) => v !== id) }),
    });
  });
  values.org.forEach((id) => {
    const name = options?.orgs.find((o) => o.id === id)?.name ?? String(id);
    chips.push({
      key: `org-${id}`,
      label: `기관: ${name}`,
      onDelete: () => onChange({ ...values, org: values.org.filter((v) => v !== id) }),
    });
  });
  values.org_category.forEach((c) =>
    chips.push({
      key: `org_category-${c}`,
      label: `기관 분야: ${c}`,
      onDelete: () => onChange({ ...values, org_category: values.org_category.filter((v) => v !== c) }),
    }),
  );
  selectedChannels(options?.channels ?? [], values.source).forEach((c) => {
    chips.push({
      key: `channel-${c.name}`,
      label: `데이터 소스: ${c.name}`,
      onDelete: () => onChange({ ...values, source: values.source.filter((id) => !c.source_ids.includes(id)) }),
    });
  });
  values.region.forEach((r) =>
    chips.push({
      key: `region-${r}`,
      label: `지역: ${r}`,
      onDelete: () => onChange({ ...values, region: values.region.filter((v) => v !== r) }),
    }),
  );
  values.stage.forEach((s) =>
    chips.push({
      key: `stage-${s}`,
      label: `단계: ${s}`,
      onDelete: () => onChange({ ...values, stage: values.stage.filter((v) => v !== s) }),
    }),
  );
  values.biz_type.forEach((b) =>
    chips.push({
      key: `biz_type-${b}`,
      label: `업무구분: ${b}`,
      onDelete: () => onChange({ ...values, biz_type: values.biz_type.filter((v) => v !== b) }),
    }),
  );
  values.work_type.forEach((w) =>
    chips.push({
      key: `work_type-${w}`,
      label: `사업유형: ${w}`,
      onDelete: () => onChange({ ...values, work_type: values.work_type.filter((v) => v !== w) }),
    }),
  );
  if (values.price_min || values.price_max) {
    chips.push({
      key: "price",
      label: `가격: ${values.price_min || "0"} ~ ${values.price_max || "∞"}`,
      onDelete: () => onChange({ ...values, price_min: "", price_max: "" }),
    });
  }
  if (values.close_in) {
    chips.push({
      key: "close_in",
      label: `${values.close_in}일 이내 마감`,
      onDelete: () => onChange({ ...values, close_in: "" }),
    });
  }
  if (values.status) {
    chips.push({
      key: "status",
      label: values.status === "open" ? "진행중" : "마감",
      onDelete: () => onChange({ ...values, status: "" }),
    });
  }
  if (values.qualified) {
    chips.push({
      key: "qualified",
      label: values.qualified === "true" ? "자격 충족" : "자격 미충족",
      onDelete: () => onChange({ ...values, qualified: "" }),
    });
  }
  if (values.exclude_group) {
    chips.push({
      key: "exclude_group",
      label: "제외 키워드 그룹 적용 중",
      onDelete: () => onChange({ ...values, exclude_group: false }),
    });
  }
  values.exclude_extra.forEach((w) =>
    chips.push({
      key: `exclude_extra-${w}`,
      label: `제외: ${w}`,
      onDelete: () => onChange({ ...values, exclude_extra: values.exclude_extra.filter((v) => v !== w) }),
    }),
  );

  if (chips.length === 0) return null;

  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      {chips.map((chip) => (
        <Chip key={chip.key} label={chip.label} size="small" onDelete={chip.onDelete} deleteIcon={<CloseIcon />} />
      ))}
    </Stack>
  );
}
