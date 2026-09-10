import AddIcon from "@mui/icons-material/Add";
import { Autocomplete, Chip, ClickAwayListener, Popper, Stack, TextField } from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { addNoticeTopic, removeNoticeTopic, type FilterOptions, type NoticeScore } from "@/api/notices";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

// 카드의 분류검수 4버튼(카테고리 맞음/재분류/완전무관/심층분석)을 없애면서(2026-09-05 사용자
// 지시) 유일하게 남긴 "관심주제 변경" — 기존 S1 분류검수(classification_correction, 나중에
// 규칙을 고칠 근거를 남기는 감사로그)와 달리 notice_score를 그 자리에서 바로 편집한다.
export function TopicEditor({
  noticeId,
  scores,
  allTopics,
}: {
  noticeId: number;
  scores: NoticeScore[];
  allTopics: FilterOptions["topics"];
}) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["notice", noticeId] });
  }

  const addMutation = useMutation({
    mutationFn: (topicId: number) => addNoticeTopic(noticeId, topicId),
    onSuccess: () => {
      invalidate();
      setAnchorEl(null);
    },
    onError: (error) => notify("error", apiErrorMessage(error, "관심주제 추가에 실패했습니다.")),
  });
  const removeMutation = useMutation({
    mutationFn: (topicId: number) => removeNoticeTopic(noticeId, topicId),
    onSuccess: invalidate,
    onError: (error) => notify("error", apiErrorMessage(error, "관심주제 삭제에 실패했습니다.")),
  });

  const attachedIds = new Set(scores.map((s) => s.interest_topic_id));
  const addableTopics = allTopics.filter((t) => !attachedIds.has(t.id));

  return (
    <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
      {scores.map((s) => (
        <Chip
          key={s.interest_topic_id}
          label={s.name}
          size="small"
          color="primary"
          variant="outlined"
          onDelete={() => removeMutation.mutate(s.interest_topic_id)}
          disabled={removeMutation.isPending}
        />
      ))}
      <Chip
        icon={<AddIcon fontSize="small" />}
        label="관심주제 추가"
        size="small"
        variant="outlined"
        onClick={(e) => setAnchorEl(e.currentTarget)}
        disabled={addMutation.isPending}
      />
      {anchorEl && (
        <ClickAwayListener onClickAway={() => setAnchorEl(null)}>
          <Popper open anchorEl={anchorEl} placement="bottom-start" sx={{ zIndex: 1300 }}>
            <Autocomplete
              size="small"
              autoFocus
              openOnFocus
              options={addableTopics}
              getOptionLabel={(o) => o.name}
              sx={{ width: 240, bgcolor: "background.paper", boxShadow: 3, borderRadius: 1 }}
              onChange={(_, selected) => selected && addMutation.mutate(selected.id)}
              renderInput={(params) => <TextField {...params} placeholder="주제 검색" autoFocus />}
            />
          </Popper>
        </ClickAwayListener>
      )}
    </Stack>
  );
}
