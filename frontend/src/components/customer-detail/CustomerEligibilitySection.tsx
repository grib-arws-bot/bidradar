import { Box, Button, Card, Chip, CircularProgress, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { fetchEligibilityProfile, saveEligibilityProfile, type EligibilityDraft } from "@/api/customerEligibility";
import { LoadingButton } from "@/components/LoadingButton";
import { useToast } from "@/components/ToastProvider";
import { apiErrorMessage } from "@/utils/errors";

const EMPTY_DRAFT: EligibilityDraft = {
  company_size_tier: null,
  has_research_institute: null,
  venture_cert: null,
  industry_codes: [],
  certifications: [],
};

// 3단(미입력/아니오/예) — customer_interest의 work_type_prefs 3단 토글과 같은 패턴.
// "미입력"은 NULL로 저장돼 비교기가 "확인 필요"로 처리한다(있다/없다로 단정하지 않음).
const TRISTATE_OPTIONS: { value: "unset" | "no" | "yes"; label: string }[] = [
  { value: "unset", label: "미입력" },
  { value: "no", label: "아니오" },
  { value: "yes", label: "예" },
];

function toTristate(value: boolean | null): "unset" | "no" | "yes" {
  if (value === null) return "unset";
  return value ? "yes" : "no";
}

function fromTristate(value: "unset" | "no" | "yes" | null): boolean | null {
  if (value === "yes") return true;
  if (value === "no") return false;
  return null;
}

// 입찰 자격요건 검증(2026-09-23, docs/구현스펙.md 07절) — CustomerInterestSection.tsx와
// 동일한 draft-전체치환 패턴. 이 값은 추천 점수에 절대 섞이지 않고(공고 상세의 별도 배지로만
// 노출) 공고의 구조화된 자격요건과 규칙으로 대조된다.
export function CustomerEligibilitySection({ customerId }: { customerId: number }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [draft, setDraft] = useState<EligibilityDraft>(EMPTY_DRAFT);
  const [industryCodeInput, setIndustryCodeInput] = useState("");
  const [certificationInput, setCertificationInput] = useState("");

  const profileQuery = useQuery({
    queryKey: ["eligibility-profile", customerId],
    queryFn: () => fetchEligibilityProfile(customerId),
  });

  // CustomerInterestSection.tsx와 같은 이유(2026-09-10/12) — 편집 중인 draft를 배경 재조회가
  // 조용히 덮어쓰지 않게, "마지막 동기화 이후 직접 편집한 적 없을 때만" 서버값을 반영한다.
  const lastSyncedRef = useRef<{ customerId: number; draft: EligibilityDraft } | null>(null);
  useEffect(() => {
    if (!profileQuery.data) return;
    const serverDraft: EligibilityDraft = {
      company_size_tier: profileQuery.data.company_size_tier,
      has_research_institute: profileQuery.data.has_research_institute,
      venture_cert: profileQuery.data.venture_cert,
      industry_codes: profileQuery.data.industry_codes,
      certifications: profileQuery.data.certifications,
    };
    const last = lastSyncedRef.current;
    const isCustomerSwitch = last?.customerId !== customerId;
    const isUntouchedSinceLastSync = last?.customerId === customerId && JSON.stringify(draft) === JSON.stringify(last.draft);
    if (isCustomerSwitch || isUntouchedSinceLastSync) {
      setDraft(serverDraft);
      lastSyncedRef.current = { customerId, draft: serverDraft };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileQuery.data, customerId]);

  const saveMutation = useMutation({
    mutationFn: () => saveEligibilityProfile(customerId, draft),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eligibility-profile", customerId] });
      notify("success", "자격요건 프로필을 저장했습니다.");
    },
    onError: (error) => notify("error", apiErrorMessage(error, "자격요건 프로필 저장에 실패했습니다.")),
  });

  function update(patch: Partial<EligibilityDraft>) {
    setDraft((prev) => ({ ...prev, ...patch }));
  }

  function addIndustryCode() {
    const code = industryCodeInput.trim();
    if (!code || draft.industry_codes.includes(code)) return;
    update({ industry_codes: [...draft.industry_codes, code] });
    setIndustryCodeInput("");
  }

  function addCertification() {
    const cert = certificationInput.trim();
    if (!cert || draft.certifications.includes(cert)) return;
    update({ certifications: [...draft.certifications, cert] });
    setCertificationInput("");
  }

  const companySizeTiers = profileQuery.data?.company_size_tiers ?? [];

  if (profileQuery.isLoading) {
    return <CircularProgress />;
  }

  return (
    <Card sx={{ p: 3 }}>
      <Typography variant="h3" sx={{ mb: 0.5 }}>
        입찰 자격요건
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
        자사 프로필을 입력하면 공고 상세에서 참여 자격(기업규모·연구소 보유·벤처인증·업종·기타
        인증)을 자동으로 대조해 보여줍니다. 추천 점수와는 무관한 별도 필터입니다.
      </Typography>
      <Stack spacing={3}>
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            기업규모
          </Typography>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={draft.company_size_tier ?? "unset"}
            onChange={(_, value) => value && update({ company_size_tier: value === "unset" ? null : value })}
          >
            <ToggleButton value="unset">미입력</ToggleButton>
            {companySizeTiers.map((tier) => (
              <ToggleButton key={tier} value={tier}>
                {tier}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Box>

        <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              연구소 보유
            </Typography>
            <ToggleButtonGroup
              size="small"
              exclusive
              value={toTristate(draft.has_research_institute)}
              onChange={(_, value) => update({ has_research_institute: fromTristate(value) })}
            >
              {TRISTATE_OPTIONS.map((o) => (
                <ToggleButton key={o.value} value={o.value}>
                  {o.label}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
          </Box>

          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              벤처기업 인증
            </Typography>
            <ToggleButtonGroup
              size="small"
              exclusive
              value={toTristate(draft.venture_cert)}
              onChange={(_, value) => update({ venture_cert: fromTristate(value) })}
            >
              {TRISTATE_OPTIONS.map((o) => (
                <ToggleButton key={o.value} value={o.value}>
                  {o.label}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
          </Box>
        </Stack>

        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            보유 업종(업종코드 또는 업종명)
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
            <TextField
              size="small"
              placeholder="예: 62010, 소프트웨어 개발업"
              value={industryCodeInput}
              onChange={(e) => setIndustryCodeInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addIndustryCode()}
              fullWidth
            />
            <Button variant="outlined" onClick={addIndustryCode}>
              추가
            </Button>
          </Stack>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {draft.industry_codes.map((code) => (
              <Chip
                key={code}
                label={code}
                onDelete={() => update({ industry_codes: draft.industry_codes.filter((c) => c !== code) })}
              />
            ))}
          </Stack>
        </Box>

        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            기타 보유 인증
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
            <TextField
              size="small"
              placeholder="예: ISO 9001"
              value={certificationInput}
              onChange={(e) => setCertificationInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addCertification()}
              fullWidth
            />
            <Button variant="outlined" onClick={addCertification}>
              추가
            </Button>
          </Stack>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {draft.certifications.map((cert) => (
              <Chip
                key={cert}
                label={cert}
                onDelete={() => update({ certifications: draft.certifications.filter((c) => c !== cert) })}
              />
            ))}
          </Stack>
        </Box>

        <Stack direction="row" spacing={2} alignItems="center">
          <LoadingButton
            variant="contained"
            size="large"
            loading={saveMutation.isPending}
            loadingText="저장 중..."
            onClick={() => saveMutation.mutate()}
          >
            저장
          </LoadingButton>
        </Stack>
      </Stack>
    </Card>
  );
}
