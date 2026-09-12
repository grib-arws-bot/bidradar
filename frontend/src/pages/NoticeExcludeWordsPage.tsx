import AddIcon from "@mui/icons-material/AddOutlined";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import { Box, Card, Stack, TextField, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createNoticeExcludeWord,
  deleteNoticeExcludeWord,
  fetchNoticeExcludeWords,
} from "@/api/noticeExcludeWords";
import { LoadingButton, LoadingIconButton } from "@/components/LoadingButton";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

// 공고 탐색 제목 제외 키워드 관리(2026-09-13 사용자 지시) — "감리·모집·고도화·유지보수"처럼
// 제목에 있으면 보고 싶지 않은 단어를 저장해두는 화면. 관리 편의를 위해 그룹은 이 목록
// 하나뿐 — 공고 탐색 화면에서 이 목록 전체를 한 번에 켜고 끌 수 있다(NoticeFilterBar.tsx).
// keyword_rule(관심주제 L2 채점용, "관심주제 분류" 화면)과는 완전히 별개.
export function NoticeExcludeWordsPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const { data, isLoading } = useQuery({ queryKey: ["notice-exclude-words"], queryFn: fetchNoticeExcludeWords });
  const [term, setTerm] = useState("");

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["notice-exclude-words"] });

  const createMutation = useMutation({
    mutationFn: createNoticeExcludeWord,
    onSuccess: () => {
      invalidate();
      setTerm("");
      notify("success", "제외 단어를 추가했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "제외 단어 추가에 실패했습니다.")),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteNoticeExcludeWord,
    onSuccess: () => {
      invalidate();
      notify("success", "제외 단어를 삭제했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "삭제에 실패했습니다.")),
  });

  function handleAdd() {
    const trimmed = term.trim();
    if (!trimmed) return;
    createMutation.mutate(trimmed);
  }

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h2">제외 키워드</Typography>
        <Typography variant="body2" color="text.secondary">
          공고 탐색 화면에서 제목에 이 단어들이 있으면 보이지 않게 걸러낼 수 있습니다. 그룹은
          관리 편의를 위해 이 목록 하나뿐이며, 공고 탐색 화면에서 통째로 켜고 끌 수 있습니다.
        </Typography>
      </Box>

      <Card sx={{ p: 3 }}>
        <Stack direction="row" spacing={1.5} sx={{ mb: 2 }}>
          <TextField
            size="small"
            placeholder="예: 감리, 모집, 고도화, 유지보수"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAdd();
            }}
            sx={{ maxWidth: 320 }}
          />
          <LoadingButton
            variant="contained"
            startIcon={<AddIcon />}
            loading={createMutation.isPending}
            loadingText="추가 중..."
            disabled={!term.trim()}
            onClick={handleAdd}
          >
            추가
          </LoadingButton>
        </Stack>

        {isLoading ? (
          <Typography variant="body2" color="text.secondary">
            불러오는 중...
          </Typography>
        ) : !data || data.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            등록된 제외 단어가 없습니다.
          </Typography>
        ) : (
          <Stack direction="row" flexWrap="wrap" useFlexGap spacing={1}>
            {data.map((w) => (
              <Stack
                key={w.id}
                direction="row"
                alignItems="center"
                spacing={0.5}
                sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, pl: 1.5, pr: 0.5, py: 0.25 }}
              >
                <Typography variant="body2">{w.term}</Typography>
                <LoadingIconButton
                  size="small"
                  loading={deleteMutation.isPending && deleteMutation.variables === w.id}
                  onClick={() => deleteMutation.mutate(w.id)}
                >
                  <DeleteIcon fontSize="small" />
                </LoadingIconButton>
              </Stack>
            ))}
          </Stack>
        )}
      </Card>
    </Stack>
  );
}
