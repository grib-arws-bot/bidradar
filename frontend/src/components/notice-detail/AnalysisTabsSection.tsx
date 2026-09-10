import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { Box, Card, Chip, Stack, Tab, Table, TableBody, TableCell, TableHead, TableRow, Tabs, Typography } from "@mui/material";

import {
  fetchRequirements,
  type AnalysisContentItem,
  type AnalysisEvaluationItem,
  type AnalysisSummary,
  type ExtractionResult,
  type Requirement,
} from "@/api/analysis";

const OP_LABEL: Record<string, string> = { gte: "이상", lte: "이하", eq: "일치", contains: "포함", manual: "서술형" };

const TAB_LABELS = ["사업목표(원문)", "사업내용(AI요약)", "사업비(중소기업)", "신청자격", "제안제출", "평가기준(원문)", "기타사항"];

type RequirementsQuery = UseQueryResult<Awaited<ReturnType<typeof fetchRequirements>>>;

export function AnalysisTabsSection({
  requirementsQuery,
  extraction,
}: {
  requirementsQuery: RequirementsQuery;
  extraction?: ExtractionResult | null;
}) {
  const [tab, setTab] = useState(0);
  const summary = requirementsQuery.data?.summary;
  const requirements = requirementsQuery.data?.requirements ?? [];
  // 채널(IRIS/나라장터)로 하드코딩하지 않는다 — A2가 실제로 끝났는지만 본다(2026-09-05 요청,
  // "채널별로 다르게"가 아니라 "완료 여부를 보여달라"는 취지 — 지금은 IRIS는 이미 실행했고
  // 나라장터는 아직 안 해서 결과적으로 채널마다 다르게 보일 뿐).
  const analysisDone = requirementsQuery.data?.step === "A2_structure";
  const extractionDone = !!extraction && (extraction.docs?.length ?? 0) > 0;

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
          label={analysisDone ? "AI분석 완료" : "AI분석 미완료"}
          size="small"
          color={analysisDone ? "success" : "default"}
          variant={analysisDone ? "filled" : "outlined"}
        />
      </Stack>

      <Box>
        {!summary && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
            아직 분석되지 않았습니다 — 위 "AI분석 실행" 버튼을 눌러주세요.
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

function requirementValueLabel(req: Requirement): string {
  return req.req_value ? `${req.req_value}${req.req_unit ?? ""} ${OP_LABEL[req.op]}` : OP_LABEL[req.op];
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
