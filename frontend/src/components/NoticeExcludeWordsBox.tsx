import AddIcon from "@mui/icons-material/AddOutlined";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import { Autocomplete, Card, Chip, FormControlLabel, Stack, Switch, TextField, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createNoticeExcludeWord,
  deleteNoticeExcludeWord,
  fetchNoticeExcludeWords,
} from "@/api/noticeExcludeWords";
import type { NoticeFilterValues } from "@/components/NoticeFilterBar";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

interface Props {
  values: NoticeFilterValues;
  onChange: (values: NoticeFilterValues) => void;
}

// 제목 제외 키워드(2026-09-13, 사용자 지시로 별도 관리 화면 대신 공고 탐색 페이지 인라인
// 박스로 통합) — 그룹(관리 편의상 1개뿐, 영구 저장 목록)을 이 박스에서 직접 추가·삭제하고
// 켜고 끄며, 이번 조회에만 쓸 즉석 단어(저장 안 됨)도 같은 박스에서 더할 수 있다.
export function NoticeExcludeWordsBox({ values, onChange }: Props) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const { data: excludeWords } = useQuery({ queryKey: ["notice-exclude-words"], queryFn: fetchNoticeExcludeWords });
  const [term, setTerm] = useState("");

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["notice-exclude-words"] });

  const createMutation = useMutation({
    mutationFn: createNoticeExcludeWord,
    onSuccess: () => {
      invalidate();
      setTerm("");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "제외 단어 추가에 실패했습니다.")),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteNoticeExcludeWord,
    onSuccess: invalidate,
    onError: (error) => notify("error", apiErrorMessage(error, "삭제에 실패했습니다.")),
  });

  function handleAdd() {
    const trimmed = term.trim();
    if (!trimmed) return;
    createMutation.mutate(trimmed);
  }

  return (
    <Card variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="subtitle2">제외 키워드</Typography>
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={values.exclude_group}
                onChange={(e) => onChange({ ...values, exclude_group: e.target.checked })}
              />
            }
            label="그룹 적용"
          />
        </Stack>

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
          {(excludeWords ?? []).map((w) => (
            <Chip
              key={w.id}
              label={w.term}
              size="small"
              onDelete={() => deleteMutation.mutate(w.id)}
              deleteIcon={<DeleteIcon fontSize="small" />}
            />
          ))}
          {excludeWords && excludeWords.length === 0 && (
            <Typography variant="caption" color="text.secondary">
              등록된 단어가 없습니다.
            </Typography>
          )}
        </Stack>

        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            size="small"
            placeholder="예: 감리, 모집, 고도화, 유지보수"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAdd();
            }}
            sx={{ maxWidth: 280 }}
          />
          <Chip
            icon={<AddIcon fontSize="small" />}
            label="그룹에 추가"
            size="small"
            color="primary"
            variant="outlined"
            onClick={handleAdd}
            disabled={!term.trim() || createMutation.isPending}
          />
        </Stack>

        <Autocomplete
          multiple
          freeSolo
          size="small"
          options={[]}
          value={values.exclude_extra}
          onChange={(_, selected) => onChange({ ...values, exclude_extra: selected as string[] })}
          renderInput={(params) => <TextField {...params} label="이번 조회에만 제외할 단어(엔터로 추가, 저장 안 됨)" />}
        />
      </Stack>
    </Card>
  );
}
