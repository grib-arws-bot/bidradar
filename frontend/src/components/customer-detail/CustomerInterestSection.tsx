import {
  Box,
  Button,
  Card,
  Chip,
  CircularProgress,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { fetchInterestProfile, saveInterestProfile, type InterestDraft, type TopicPriority } from "@/api/customerInterests";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

const EMPTY_DRAFT: InterestDraft = {
  topic_ids: [],
  topic_priorities: {},
  terms: [],
  followed_org_ids: [],
  price_min: null,
};

const PRIORITY_OPTIONS: { value: TopicPriority; label: string }[] = [
  { value: "high", label: "높음" },
  { value: "normal", label: "보통" },
  { value: "low", label: "낮음" },
];

// 관심주제 설정(S7) — 2026-09-05 사용자 지시로 대폭 축소: 팔로우 기관·미리보기·저장한 검색·
// 추정가격·지역을 없앴다. 이 시스템은 고객이 직접 로그인해 공고를 탐색·저장·팔로우하는
// 구조가 아니라 관리자가 값을 대신 설정하는 구조라 그 셋은 실제로 쓰이지 않았다. 리포트
// 생성·목록·AI 코멘트는 "보고서 관리"로 분리.
// 2026-09-07 — 금액 하한만 다시 도입(→ 위 결정 일부 변경, 의사결정_로그 참고). 상한·지역은
// 여전히 없음.
export function CustomerInterestSection({ customerId }: { customerId: number }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [draft, setDraft] = useState<InterestDraft>(EMPTY_DRAFT);
  const [termInput, setTermInput] = useState("");

  const profileQuery = useQuery({
    queryKey: ["interest-profile", customerId],
    queryFn: () => fetchInterestProfile(customerId),
  });

  // 2026-09-10 버그 수정 — 이 effect가 profileQuery.data가 바뀔 때마다(react-query가 배경에서
  // 재조회할 때마다) 무조건 draft를 덮어썼다. 사용자가 우선순위를 "높음"으로 바꾸고 "저장"을
  // 누르기 전에 어떤 이유로든 재조회가 한 번 일어나면 방금 바꾼 값이 저장 전에 조용히 서버의
  // 예전 값(대부분 "보통")으로 되돌아간다 — "우선순위가 계속 보통으로 바뀐다"는 제보의 원인.
  //
  // 2026-09-12 재수정 — 위 수정을 "customerId가 실제로 바뀌었을 때만 동기화"로 했더니, 이번엔
  // 반대 문제가 생겼다: AI 프로필 요약이 관심주제를 자동 설정해도(customer_profile.py) 같은
  // 고객 화면에 머무는 동안은 재조회돼도 화면에 반영이 안 돼 새로고침해야만 보였다. 진짜
  // 구분해야 할 기준은 "고객이 바뀌었는가"가 아니라 "사용자가 마지막 동기화 이후 직접 뭔가
  // 편집했는가"다 — 편집한 적 없으면(=draft가 마지막으로 동기화한 서버값 그대로면) 서버가
  // 뭘로 바꿨든 안전하게 반영해도 되고, 편집 중이면 그대로 안 건드린다.
  const lastSyncedRef = useRef<{ customerId: number; draft: InterestDraft } | null>(null);
  useEffect(() => {
    if (!profileQuery.data) return;
    const serverDraft: InterestDraft = {
      topic_ids: profileQuery.data.topic_ids,
      topic_priorities: profileQuery.data.topic_priorities,
      terms: profileQuery.data.terms,
      followed_org_ids: profileQuery.data.followed_org_ids,
      price_min: profileQuery.data.price_min,
    };
    const last = lastSyncedRef.current;
    const isCustomerSwitch = last?.customerId !== customerId;
    const isUntouchedSinceLastSync = last?.customerId === customerId && JSON.stringify(draft) === JSON.stringify(last.draft);
    if (isCustomerSwitch || isUntouchedSinceLastSync) {
      setDraft(serverDraft);
      lastSyncedRef.current = { customerId, draft: serverDraft };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- draft는 비교용으로만 읽는다(동기화 트리거로 넣으면 매 편집마다 재실행돼 의미가 없어짐)
  }, [profileQuery.data, customerId]);

  // saveMutation에 onError가 없어서 저장이 실패해도 아무 표시가 없던 문제(2026-09-07 발견,
  // 71번 항목과 같은 "조용한 실패" 패턴) — 성공·실패 모두 토스트로 알린다.
  const saveMutation = useMutation({
    mutationFn: () => saveInterestProfile(customerId, draft),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["interest-profile", customerId] });
      notify("success", "관심 주제를 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "관심 주제 저장에 실패했습니다.")),
  });

  function update(patch: Partial<InterestDraft>) {
    setDraft((prev) => ({ ...prev, ...patch }));
  }

  function addTerm() {
    const term = termInput.trim();
    if (!term || draft.terms.includes(term)) return;
    update({ terms: [...draft.terms, term] });
    setTermInput("");
  }

  function setPriority(topicId: number, priority: TopicPriority | null) {
    if (!priority) return; // ToggleButtonGroup(exclusive)는 이미 선택된 값을 다시 누르면 null을 준다 — 무시
    update({ topic_priorities: { ...draft.topic_priorities, [String(topicId)]: priority } });
  }

  const topics = profileQuery.data?.topics ?? [];
  const selectedTopics = draft.topic_ids
    .map((id) => topics.find((t) => t.id === id))
    .filter((t): t is { id: number; name: string } => t != null);

  if (profileQuery.isLoading) {
    return <CircularProgress />;
  }

  return (
    <Card sx={{ p: 3 }}>
      <Typography variant="h3" sx={{ mb: 2 }}>
        관심 주제
      </Typography>
      <Stack spacing={3}>
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
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
                      topic_ids: active ? draft.topic_ids.filter((id) => id !== t.id) : [...draft.topic_ids, t.id],
                    })
                  }
                />
              );
            })}
          </Stack>
        </Box>

        {selectedTopics.length > 0 && (
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              선택한 주제 우선순위
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              회사 핵심 사업 주제는 "높음"으로 — 매칭 점수가 더 높게 반영되어 리포트 상위에 뜹니다.
            </Typography>
            <Stack spacing={0.5}>
              {selectedTopics.map((t) => (
                <Stack key={t.id} direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2">{t.name}</Typography>
                  <ToggleButtonGroup
                    size="small"
                    exclusive
                    value={draft.topic_priorities[String(t.id)] ?? "normal"}
                    onChange={(_, value) => setPriority(t.id, value)}
                  >
                    {PRIORITY_OPTIONS.map((o) => (
                      <ToggleButton key={o.value} value={o.value}>
                        {o.label}
                      </ToggleButton>
                    ))}
                  </ToggleButtonGroup>
                </Stack>
              ))}
            </Stack>
          </Box>
        )}

        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            금액 하한
          </Typography>
          <TextField
            size="small"
            type="number"
            label="이 금액 이상만 추천(만원)"
            value={draft.price_min !== null ? draft.price_min / 10000 : ""}
            onChange={(e) => {
              const raw = e.target.value;
              update({ price_min: raw === "" ? null : Math.max(0, Math.round(Number(raw) * 10000)) });
            }}
            slotProps={{ htmlInput: { min: 0, step: 100 } }}
            sx={{ width: 220 }}
            helperText="추정가격이 이 금액 미만이거나 미공개인 공고는 추천에서 제외됩니다. 비워두면 제한 없음."
          />
        </Box>

        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
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
            {draft.terms.map((term) => (
              <Chip key={term} label={term} onDelete={() => update({ terms: draft.terms.filter((t) => t !== term) })} />
            ))}
          </Stack>
        </Box>

        <Stack direction="row" spacing={2} alignItems="center">
          <Button variant="contained" size="large" disabled={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            저장
          </Button>
        </Stack>
      </Stack>
    </Card>
  );
}
