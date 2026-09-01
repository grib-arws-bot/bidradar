import {
  Autocomplete,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
} from "@mui/material";
import { useState } from "react";

import type { ClassificationAction } from "@/api/classification";
import type { FilterOptions } from "@/api/notices";

const REASON_PRESETS = ["범위 밖", "규모 부적합", "자격 미충족", "경쟁 불리", "기타"];

interface Props {
  open: boolean;
  action: Extract<ClassificationAction, "recategorize" | "irrelevant">;
  topics: FilterOptions["topics"];
  submitting: boolean;
  onClose: () => void;
  onSubmit: (payload: { categories?: number[]; reason?: string }) => void;
}

// S1 분류검수(구현스펙 06절) — 재분류는 대분류 다중선택 최소 1개, 완전 무관은 사유 필수.
export function ClassificationDialog({ open, action, topics, submitting, onClose, onSubmit }: Props) {
  const [categories, setCategories] = useState<number[]>([]);
  const [preset, setPreset] = useState<string | null>(null);
  const [customReason, setCustomReason] = useState("");

  const reason = preset === "기타" || preset === null ? customReason : preset;
  const canSubmit = action === "recategorize" ? categories.length > 0 : reason.trim().length > 0;

  function handleClose() {
    setCategories([]);
    setPreset(null);
    setCustomReason("");
    onClose();
  }

  function handleSubmit() {
    if (!canSubmit) return;
    if (action === "recategorize") {
      onSubmit({ categories });
    } else {
      onSubmit({ reason: reason.trim() });
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="xs">
      <DialogTitle>{action === "recategorize" ? "카테고리 재분류" : "완전 무관 처리"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {action === "recategorize" ? (
            <Autocomplete
              multiple
              options={topics}
              getOptionLabel={(o) => o.name}
              isOptionEqualToValue={(a, b) => a.id === b.id}
              value={topics.filter((t) => categories.includes(t.id))}
              onChange={(_, selected) => setCategories(selected.map((s) => s.id))}
              renderInput={(params) => (
                <TextField {...params} label="올바른 대분류(최소 1개)" autoFocus />
              )}
            />
          ) : (
            <>
              <ToggleButtonGroup
                value={preset}
                exclusive
                onChange={(_, value) => setPreset(value)}
                orientation="vertical"
                fullWidth
              >
                {REASON_PRESETS.map((p) => (
                  <ToggleButton key={p} value={p} sx={{ justifyContent: "flex-start" }}>
                    {p}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
              {(preset === "기타" || preset === null) && (
                <TextField
                  label="사유 직접 입력"
                  value={customReason}
                  onChange={(e) => setCustomReason(e.target.value)}
                  multiline
                  minRows={2}
                  autoFocus={preset === "기타"}
                />
              )}
            </>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>취소</Button>
        <Button variant="contained" disabled={!canSubmit || submitting} onClick={handleSubmit}>
          제출
        </Button>
      </DialogActions>
    </Dialog>
  );
}
