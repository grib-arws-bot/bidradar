import AddIcon from "@mui/icons-material/AddOutlined";
import { Chip, IconButton, MenuItem, Stack, TextField, Tooltip } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createKeyword,
  deleteKeyword,
  fetchKeywords,
  updateKeyword,
  type WeightClass,
} from "@/api/keywords";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

const WEIGHT_CLASS_OPTIONS: { value: WeightClass; label: string }[] = [
  { value: "core", label: "core" },
  { value: "tech", label: "tech" },
  { value: "ctx", label: "ctx" },
  { value: "block", label: "block" },
];

// 관심주제 키워드(L2 규칙) 관리(2026-09-05 신설, "관심주제 분류" 테이블의 "키워드" 열에
// 바로 표시) — 공고 "제목"에 이 단어가 포함되면 점수를 준다(app/collector/scorer.py).
// 칩을 클릭하면 활성/비활성 토글, x를 누르면 완전히 삭제(다른 레지스트리와 달리 keyword_rule은
// 참조하는 테이블이 없어 하드 삭제를 허용).
export function TopicKeywordsSection({ topicId }: { topicId: number }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const keywordsQuery = useQuery({ queryKey: ["topic-keywords", topicId], queryFn: () => fetchKeywords(topicId) });

  const [adding, setAdding] = useState(false);
  const [term, setTerm] = useState("");
  const [weightClass, setWeightClass] = useState<WeightClass>("tech");
  const [weight, setWeight] = useState(2);

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["topic-keywords", topicId] });
  }

  const createMutation = useMutation({
    mutationFn: () => createKeyword(topicId, { term: term.trim(), weight_class: weightClass, weight }),
    onSuccess: () => {
      invalidate();
      setTerm("");
      setAdding(false);
      notify("success", "키워드를 추가했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "키워드 추가에 실패했습니다.")),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) => updateKeyword(id, { active }),
    onSuccess: invalidate,
    onError: (error) => notify("error", apiErrorMessage(error, "키워드 상태 변경에 실패했습니다.")),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteKeyword(id),
    onSuccess: invalidate,
    onError: (error) => notify("error", apiErrorMessage(error, "키워드 삭제에 실패했습니다.")),
  });

  return (
    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap alignItems="center" sx={{ minWidth: 260 }}>
      {(keywordsQuery.data ?? []).map((k) => (
        <Tooltip key={k.id} title={`${k.weight_class} ${k.weight >= 0 ? "+" : ""}${k.weight} · 클릭하면 ${k.active ? "비활성화" : "활성화"}`}>
          <Chip
            size="small"
            label={k.term}
            variant={k.active ? "filled" : "outlined"}
            color={k.active ? "primary" : "default"}
            onClick={() => toggleMutation.mutate({ id: k.id, active: !k.active })}
            onDelete={() => deleteMutation.mutate(k.id)}
          />
        </Tooltip>
      ))}

      {adding ? (
        <Stack direction="row" spacing={0.5} alignItems="center">
          <TextField
            size="small"
            autoFocus
            placeholder="키워드"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && term.trim() && createMutation.mutate()}
            sx={{ width: 110 }}
          />
          <TextField
            select
            size="small"
            value={weightClass}
            onChange={(e) => setWeightClass(e.target.value as WeightClass)}
            sx={{ width: 80 }}
          >
            {WEIGHT_CLASS_OPTIONS.map((o) => (
              <MenuItem key={o.value} value={o.value}>
                {o.label}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            size="small"
            type="number"
            value={weight}
            onChange={(e) => setWeight(Number(e.target.value))}
            sx={{ width: 60 }}
          />
          <IconButton size="small" disabled={!term.trim() || createMutation.isPending} onClick={() => createMutation.mutate()}>
            <AddIcon fontSize="small" />
          </IconButton>
        </Stack>
      ) : (
        <Tooltip title="키워드 추가">
          <IconButton size="small" onClick={() => setAdding(true)}>
            <AddIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
    </Stack>
  );
}
