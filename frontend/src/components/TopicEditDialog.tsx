import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField } from "@mui/material";
import { useEffect, useState } from "react";

import type { Topic } from "@/api/topics";

interface Props {
  open: boolean;
  topic: Topic | null; // null이면 새로 만들기
  submitting: boolean;
  onClose: () => void;
  onSubmit: (payload: { name: string; description: string | null; sort_order: number }) => void;
}

// 관심주제 대분류(L2-b, 20개 초안) 관리자 CRUD — 2026-09-01 요청.
export function TopicEditDialog({ open, topic, submitting, onClose, onSubmit }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [sortOrder, setSortOrder] = useState(0);

  useEffect(() => {
    if (open) {
      setName(topic?.name ?? "");
      setDescription(topic?.description ?? "");
      setSortOrder(topic?.sort_order ?? 0);
    }
  }, [open, topic]);

  const canSubmit = name.trim().length > 0;

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>{topic ? "분류 수정" : "새 분류 추가"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField label="이름" value={name} onChange={(e) => setName(e.target.value)} autoFocus fullWidth />
          <TextField
            label="설명(선택)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            multiline
            minRows={2}
            fullWidth
          />
          <TextField
            label="정렬 순서"
            type="number"
            value={sortOrder}
            onChange={(e) => setSortOrder(Number(e.target.value))}
            helperText="목록에서 낮은 숫자가 먼저 나옵니다"
            fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>취소</Button>
        <Button
          variant="contained"
          disabled={!canSubmit || submitting}
          onClick={() => onSubmit({ name: name.trim(), description: description.trim() || null, sort_order: sortOrder })}
        >
          저장
        </Button>
      </DialogActions>
    </Dialog>
  );
}
