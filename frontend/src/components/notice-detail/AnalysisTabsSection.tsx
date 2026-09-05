import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { Box, Card, Stack, Tab, Table, TableBody, TableCell, TableHead, TableRow, Tabs, Typography } from "@mui/material";

import { fetchRequirements, type AnalysisContentItem, type AnalysisEvaluationItem, type AnalysisSummary, type Requirement } from "@/api/analysis";

const OP_LABEL: Record<string, string> = { gte: "이상", lte: "이하", eq: "일치", contains: "포함", manual: "서술형" };
// 신청자격·평가기준은 각자 탭에서 다루므로, 여기(기타사항)엔 그 외 분류만 — 사용자가
// "특별한 성능·실적 등"이라고 명시한 것과 일치.
const OTHER_REQ_CATEGORIES = ["성능", "인증", "실적", "인력", "기타"];

const TAB_LABELS = ["사업목표(원문)", "사업내용(AI요약)", "사업비(중소기업)", "신청자격", "제안제출", "평가기준(원문)", "기타사항"];

type RequirementsQuery = UseQueryResult<Awaited<ReturnType<typeof fetchRequirements>>>;

export function AnalysisTabsSection({ requirementsQuery }: { requirementsQuery: RequirementsQuery }) {
  const [tab, setTab] = useState(0);
  const summary = requirementsQuery.data?.summary;
  const requirements = requirementsQuery.data?.requirements ?? [];

  return (
    <Card sx={{ p: 3 }}>
      <Typography variant="h3" sx={{ mb: 1.5 }}>
        AI분석정보
      </Typography>

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
          {tab === 1 && <ContentItemsTab items={summary.content_items} />}
          {tab === 2 && <BudgetTab projectBudget={summary.project_budget} conditions={summary.budget_conditions} />}
          {tab === 3 && <EligibilityTab eligibility={summary.eligibility} />}
          {tab === 4 && <SubmissionTab submission={summary.submission} />}
          {tab === 5 && <EvaluationTab evaluation={summary.evaluation} />}
          {tab === 6 && <OtherNotesTab notes={summary.other_notes} requirements={requirements} />}
        </>
      )}
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

function ContentItemsTab({ items }: { items: AnalysisContentItem[] }) {
  if (items.length === 0) return <EmptyNote>사업내용을 찾지 못했습니다.</EmptyNote>;
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
          </Stack>
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
            {item.summary}
          </Typography>
        </Box>
      ))}
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
  return (
    <Stack spacing={2}>
      <Table size="small">
        <TableBody>
          <LabeledRow label="제출기한" value={submission.deadline} />
          <LabeledRow label="제출방법/사이트" value={submission.method} />
        </TableBody>
      </Table>
      <Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
          제출서류
        </Typography>
        {submission.documents.length === 0 ? (
          <Typography variant="body2">—</Typography>
        ) : (
          <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
            {submission.documents.map((doc, i) => (
              <Typography key={i} component="li" variant="body2">
                {doc}
              </Typography>
            ))}
          </Box>
        )}
      </Box>
    </Stack>
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
  const grouped = OTHER_REQ_CATEGORIES.map((category) => ({
    category,
    items: requirements.filter((r) => r.category === category),
  })).filter((g) => g.items.length > 0);

  return (
    <Stack spacing={2}>
      {notes ? (
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
          {notes}
        </Typography>
      ) : (
        <EmptyNote>기타 특이사항이 없습니다.</EmptyNote>
      )}

      {grouped.map(({ category, items }) => (
        <Box key={category}>
          <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
            {category}
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>요구사항</TableCell>
                <TableCell>기준값</TableCell>
                <TableCell>조문 위치</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((req, i) => (
                <TableRow key={i}>
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
        </Box>
      ))}
    </Stack>
  );
}
