import CloseIcon from "@mui/icons-material/Close";
import {
  Autocomplete,
  Chip,
  MenuItem,
  Stack,
  TextField,
} from "@mui/material";

import type { FilterOptions } from "@/api/notices";

export interface NoticeFilterValues {
  domain: number[];
  org: number[];
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
}

export const EMPTY_FILTERS: NoticeFilterValues = {
  domain: [],
  org: [],
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
};

interface Props {
  options: FilterOptions | undefined;
  values: NoticeFilterValues;
  onChange: (values: NoticeFilterValues) => void;
}

// 필터 9종(구현스펙 04절): domain·org·source·price(min+max 합쳐 1종)·region·stage·close_in·status·qualified
export function NoticeFilterBar({ options, values, onChange }: Props) {
  const set = <K extends keyof NoticeFilterValues>(key: K, value: NoticeFilterValues[K]) =>
    onChange({ ...values, [key]: value });

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
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
          sx={{ minWidth: 200 }}
          options={options?.sources ?? []}
          getOptionLabel={(o) => o.name}
          value={(options?.sources ?? []).filter((s) => values.source.includes(s.id))}
          onChange={(_, selected) => set("source", selected.map((s) => s.id))}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => <TextField {...params} label="소스" />}
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
      <AppliedChips options={options} values={values} onChange={onChange} />
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
  values.source.forEach((id) => {
    const name = options?.sources.find((s) => s.id === id)?.name ?? String(id);
    chips.push({
      key: `source-${id}`,
      label: `소스: ${name}`,
      onDelete: () => onChange({ ...values, source: values.source.filter((v) => v !== id) }),
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

  if (chips.length === 0) return null;

  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      {chips.map((chip) => (
        <Chip key={chip.key} label={chip.label} size="small" onDelete={chip.onDelete} deleteIcon={<CloseIcon />} />
      ))}
    </Stack>
  );
}
