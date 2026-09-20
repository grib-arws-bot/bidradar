import { Box, Card, Chip, Stack, Tab, Table, TableBody, TableCell, TableHead, TableRow, Tabs, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import {
  fetchSllmRequirementPreview,
  startSllmRequirementPreview,
  type AnalysisContentItem,
  type AnalysisEvaluationItem,
  type AnalysisSummary,
  type ExtractionResult,
  type Requirement,
  type RequirementsResult,
} from "@/api/analysis";
import { useToast } from "@/components/ToastProvider";

import { requirementValueLabel } from "./requirementFormat";
import { SllmPreviewInline } from "./SllmPreviewInline";

const TAB_LABELS = ["사업목표(원문)", "사업내용(AI요약)", "사업비(중소기업)", "신청자격", "제안제출", "평가기준(원문)", "기타사항"];

// 관리자 공고탐색(NoticeDetailPage)과 공개 리포트(PublicNoticeDetailPage)가 함께 쓴다
// (2026-09-12 — "공고탐색과 같은 내용이 리포트에도 보이게" 요청). react-query 객체가 아니라
// 순수 데이터를 받아서 두 화면 다 재사용 가능하게 만들었다 — 인증된 관리자 쿼리든 공개
// 토큰 쿼리든 이 컴포넌트 입장에선 같은 모양의 데이터일 뿐이다.
//
// sLLM 미리보기(noticeId, 2026-09-20)는 noticeId가 주어질 때만 동작한다 — 관리자 화면만
// 넘겨주고 공개 리포트는 안 넘겨서 자동으로 숨겨진다(미검증 "확인 필요" 결과를 고객에게
// 보이면 안 됨). AI분석(A2, Haiku)이 이미 끝난 공고는 sLLM을 돌릴 이유가 없다 — "이 공고를
// Haiku로 분석할 가치가 있는지" 판단은 이미 A2 완료로 끝난 질문이므로, summary가 있으면
// sLLM 미리보기를 아예 실행하지 않는다(의사결정_로그 184번).
export function AnalysisTabsSection({
  requirements: requirementsData,
  extraction,
  noticeId,
}: {
  requirements: RequirementsResult | null | undefined;
  extraction?: ExtractionResult | null;
  noticeId?: number;
}) {
  const [tab, setTab] = useState(0);
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const summary = requirementsData?.summary;
  const requirements = requirementsData?.requirements ?? [];
  // 채널(IRIS/나라장터)로 하드코딩하지 않는다 — A2가 실제로 끝났는지만 본다(2026-09-05 요청,
  // "채널별로 다르게"가 아니라 "완료 여부를 보여달라"는 취지 — 지금은 IRIS는 이미 실행했고
  // 나라장터는 아직 안 해서 결과적으로 채널마다 다르게 보일 뿐).
  const analysisDone = requirementsData?.step === "A2_structure";
  const summaryOutdated = !!summary && !!requirementsData?.summary_outdated;
  const extractionDone = !!extraction && (extraction.docs?.length ?? 0) > 0;

  const sllmEnabled = !!noticeId && extractionDone && !summary;
  const sllmQueryKey = ["notice-sllm-preview", noticeId];
  const sllmPreviewQuery = useQuery({
    queryKey: sllmQueryKey,
    queryFn: () => fetchSllmRequirementPreview(noticeId!),
    enabled: sllmEnabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 3000 : false;
    },
  });
  const sllmStartMutation = useMutation({
    mutationFn: () => startSllmRequirementPreview(noticeId!),
    onSuccess: (data) => queryClient.setQueryData(sllmQueryKey, data),
    onError: (error) => {
      notify(
        "error",
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "sLLM 미리보기 시작에 실패했습니다."
      );
    },
  });
  const autoStartedNoticeId = useRef<number | null>(null);
  useEffect(() => {
    if (!sllmEnabled) return;
    if (sllmPreviewQuery.isLoading) return;
    if (sllmPreviewQuery.data) return;
    if (autoStartedNoticeId.current === noticeId) return;
    autoStartedNoticeId.current = noticeId ?? null;
    sllmStartMutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sllmEnabled, noticeId, sllmPreviewQuery.isLoading, sllmPreviewQuery.data]);
  const sllmPreview = sllmEnabled ? sllmPreviewQuery.data : undefined;

  // 원문 첨부 목록("분석대상 파일")은 페이지 최하단 별도 섹션(AnalyzedDocumentsSection)으로
  // 옮겼다(2026-09-08 요청) — 여기서는 완료 여부 배지만 제목 옆에 보여준다. "AI분석"이라는
  // 하위 제목도 삭제(같은 요청) — 위 "공고 상세분석" 제목과 배지로 이미 맥락이 드러난다.
  return (
    <Card sx={{ p: 3 }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <Typography variant="h3">공고 상세분석</Typography>
        <Chip
          label={extractionDone ? "첨부분석 완료" : "첨부분석 미완료"}
          size="small"
          color={extractionDone ? "success" : "default"}
          variant={extractionDone ? "filled" : "outlined"}
        />
        <Chip
          label={summaryOutdated ? "AI분석 완료(첨부 재추출됨 — 재분석 필요)" : analysisDone ? "AI분석 완료" : "AI분석 미완료"}
          size="small"
          color={summaryOutdated ? "warning" : analysisDone ? "success" : "default"}
          variant={analysisDone || summaryOutdated ? "filled" : "outlined"}
        />
        {sllmEnabled && sllmPreview && (
          <Chip
            label={
              sllmPreview.status === "done"
                ? "sLLM 미리보기 완료"
                : sllmPreview.status === "failed"
                  ? "sLLM 미리보기 실패"
                  : "sLLM 미리보기 진행 중"
            }
            size="small"
            color={sllmPreview.status === "done" ? "info" : sllmPreview.status === "failed" ? "error" : "default"}
            variant="outlined"
          />
        )}
      </Stack>

      <Box>
        {!summary && (
          <SllmPreviewInline
            preview={sllmPreview}
            onRetry={() => sllmStartMutation.mutate()}
            retrying={sllmStartMutation.isPending}
          />
        )}
        {summaryOutdated && (
          <Typography variant="body2" color="warning.main" sx={{ mb: 2 }}>
            첨부문서가 새로 추출된 뒤 아직 AI분석을 다시 실행하지 않았습니다 — 아래 내용은 이전
            버전 분석 결과입니다. 최신 첨부 기준으로 갱신하려면 위 "재분석"을 실행하세요.
          </Typography>
        )}

        {summary && (
          <>
            <Tabs value={tab} onChange={(_, v: number) => setTab(v)} variant="scrollable" scrollButtons="auto" sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
              {TAB_LABELS.map((label) => (
                <Tab key={label} label={label} />
              ))}
            </Tabs>

            {tab === 0 && <PurposeTab purpose={summary.purpose} />}
            {tab === 1 && <ContentItemsTab items={summary.content_items} requirements={requirements} />}
            {tab === 2 && <BudgetTab projectBudget={summary.project_budget} conditions={summary.budget_conditions} />}
            {tab === 3 && <EligibilityTab eligibility={summary.eligibility} />}
            {tab === 4 && <SubmissionTab submission={summary.submission} />}
            {tab === 5 && <EvaluationTab evaluation={summary.evaluation} />}
            {tab === 6 && <OtherNotesTab notes={summary.other_notes} requirements={requirements} />}
          </>
        )}
      </Box>
    </Card>
  );
}

function EmptyNote({ children }: { children: string }) {
  return (
    <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
      {children}
    </Typography>
  );
}

function PurposeTab({ purpose }: { purpose: string }) {
  if (!purpose) return <EmptyNote>원문에서 사업목적을 찾지 못했습니다.</EmptyNote>;
  return (
    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}>
      {purpose}
    </Typography>
  );
}

// 성능 요구사항을 과제 하위에 묶는다(2026-09-05 요청). 과제가 하나뿐이면 task_ref 유무와
// 무관하게 전부 그 과제에 붙인다 — 여러 과제일 땐 task_ref로 매칭하고, 매칭 안 되는 항목은
// 마지막에 "성능(공통)"으로 따로 보여준다(조용히 누락시키지 않음).
function groupPerformanceReqs(items: AnalysisContentItem[], requirements: Requirement[]) {
  const perf = requirements.filter((r) => r.category === "성능");
  if (items.length <= 1) {
    const byTitle = new Map<string, Requirement[]>();
    if (items.length === 1) byTitle.set(items[0].title, perf);
    return { byTitle, common: [] as Requirement[] };
  }
  const byTitle = new Map<string, Requirement[]>();
  const common: Requirement[] = [];
  for (const req of perf) {
    const item = items.find((i) => i.title === req.task_ref);
    if (item) {
      byTitle.set(item.title, [...(byTitle.get(item.title) ?? []), req]);
    } else {
      common.push(req);
    }
  }
  return { byTitle, common };
}

function PerformanceReqList({ reqs }: { reqs: Requirement[] }) {
  if (reqs.length === 0) return null;
  return (
    <Box sx={{ mt: 1.5 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
        성능 요구사항
      </Typography>
      <Table size="small">
        <TableBody>
          {reqs.map((req, i) => (
            <TableRow key={i}>
              <TableCell sx={{ border: 0, pl: 0 }}>{req.req_text}</TableCell>
              <TableCell className="tnum" sx={{ border: 0, whiteSpace: "nowrap" }}>
                {requirementValueLabel(req)}
              </TableCell>
              <TableCell sx={{ border: 0 }}>
                <Typography variant="caption" color="text.secondary">
                  {req.cite}
                </Typography>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

function ContentItemsTab({ items, requirements }: { items: AnalysisContentItem[]; requirements: Requirement[] }) {
  if (items.length === 0) return <EmptyNote>사업내용을 찾지 못했습니다.</EmptyNote>;
  const { byTitle, common } = groupPerformanceReqs(items, requirements);
  return (
    <Stack spacing={2.5} divider={<Box sx={{ borderBottom: "1px solid", borderColor: "divider" }} />}>
      {items.map((item, i) => (
        <Box key={i}>
          <Typography variant="subtitle1" fontWeight={700}>
            {items.length > 1 ? `(사업${i + 1}) ` : ""}
            {item.title}
          </Typography>
          <Stack direction="row" spacing={3} sx={{ my: 0.5 }}>
            {item.period && (
              <Typography variant="caption" color="text.secondary">
                기간: {item.period}
              </Typography>
            )}
            {item.budget && (
              <Typography variant="caption" color="text.secondary">
                사업비: {item.budget}
              </Typography>
            )}
            {item.lead_org && item.lead_org !== "제한없음" && (
              <Typography variant="caption" color="error.main" fontWeight={700}>
                주관기관 제한: {item.lead_org}
              </Typography>
            )}
          </Stack>
          {item.task_type && (item.task_type.execution_system || item.task_type.development_form || item.task_type.call_type) && (
            <Stack direction="row" spacing={0.75} sx={{ mb: 1 }}>
              {[item.task_type.execution_system, item.task_type.development_form, item.task_type.call_type]
                .filter(Boolean)
                .map((label, i) => (
                  <Chip key={i} label={label} size="small" variant="outlined" />
                ))}
            </Stack>
          )}
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
            {item.summary}
          </Typography>
          <PerformanceReqList reqs={byTitle.get(item.title) ?? []} />
        </Box>
      ))}
      {common.length > 0 && (
        <Box>
          <Typography variant="subtitle1" fontWeight={700}>
            성능(공통)
          </Typography>
          <PerformanceReqList reqs={common} />
        </Box>
      )}
    </Stack>
  );
}

function LabeledRow({ label, value }: { label: string; value: string }) {
  return (
    <TableRow>
      <TableCell sx={{ width: 220, color: "text.secondary", verticalAlign: "top" }}>{label}</TableCell>
      <TableCell sx={{ whiteSpace: "pre-wrap" }}>{value || "—"}</TableCell>
    </TableRow>
  );
}

function BudgetTab({ projectBudget, conditions }: { projectBudget: string; conditions: AnalysisSummary["budget_conditions"] }) {
  return (
    <Table size="small">
      <TableBody>
        <LabeledRow label="사업비" value={projectBudget} />
        <LabeledRow label="정부지원비율" value={conditions.government_support_ratio} />
        <LabeledRow label="현금부담비율" value={conditions.institution_cash_burden_ratio} />
        <LabeledRow label="인건비계상" value={conditions.labor_cost_basis} />
        <LabeledRow label="청년인력" value={conditions.youth_hiring_requirement} />
        <LabeledRow label="기술료징수" value={conditions.tech_fee_collection} />
      </TableBody>
    </Table>
  );
}

function EligibilityTab({ eligibility }: { eligibility: AnalysisSummary["eligibility"] }) {
  return (
    <Table size="small">
      <TableBody>
        <LabeledRow label="컨소시엄" value={eligibility.consortium} />
        <LabeledRow label="주관기관" value={eligibility.lead_org} />
        <LabeledRow label="참여기관" value={eligibility.participant_org} />
        <LabeledRow label="수요기관" value={eligibility.demand_org} />
        <LabeledRow label="기업규모" value={eligibility.company_size} />
        <LabeledRow label="특이사항" value={eligibility.special_notes} />
      </TableBody>
    </Table>
  );
}

function SubmissionTab({ submission }: { submission: AnalysisSummary["submission"] }) {
  const docs = submission.documents.length > 0 ? submission.documents : ["—"];
  return (
    <Table size="small">
      <TableBody>
        <LabeledRow label="제출기한" value={submission.deadline} />
        <LabeledRow label="제출방법/사이트" value={submission.method} />
        {docs.map((doc, i) => (
          <TableRow key={i}>
            {i === 0 && (
              <TableCell rowSpan={docs.length} sx={{ color: "text.secondary", verticalAlign: "top" }}>
                제출서류
              </TableCell>
            )}
            <TableCell>{doc}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function EvaluationTab({ evaluation }: { evaluation: AnalysisEvaluationItem[] }) {
  if (evaluation.length === 0) return <EmptyNote>평가기준을 찾지 못했습니다.</EmptyNote>;
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>항목</TableCell>
          <TableCell>배점</TableCell>
          <TableCell>세부 내용</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {evaluation.map((e, i) => (
          <TableRow key={i}>
            <TableCell sx={{ whiteSpace: "nowrap", verticalAlign: "top" }}>{e.item}</TableCell>
            <TableCell className="tnum" sx={{ whiteSpace: "nowrap", verticalAlign: "top" }}>
              {e.weight}
            </TableCell>
            <TableCell>{e.note}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}


function OtherNotesTab({ notes, requirements }: { notes: string; requirements: Requirement[] }) {
  // 기타사항은 분류별로 나누지 않는다(2026-09-05 요청) — "어떤 내용이든 특이사항이 있으면
  // 정리하는 자리"라 성능(사업내용 탭에서 과제별로 따로 보여줌)을 뺀 나머지를 한 목록으로.
  const items = requirements.filter((r) => r.category !== "성능");

  return (
    <Stack spacing={2}>
      {notes ? (
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
          {notes}
        </Typography>
      ) : (
        <EmptyNote>기타 특이사항이 없습니다.</EmptyNote>
      )}

      {items.length > 0 && (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>분류</TableCell>
              <TableCell>요구사항</TableCell>
              <TableCell>기준값</TableCell>
              <TableCell>조문 위치</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((req, i) => (
              <TableRow key={i}>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{req.category}</TableCell>
                <TableCell>{req.req_text}</TableCell>
                <TableCell className="tnum">{requirementValueLabel(req)}</TableCell>
                <TableCell>
                  <Typography variant="caption" color="text.secondary">
                    {req.cite}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Stack>
  );
}
