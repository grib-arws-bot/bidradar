import ArrowBackIcon from "@mui/icons-material/ArrowBackIosNewOutlined";
import ArrowForwardIcon from "@mui/icons-material/ArrowForwardIosOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMoreOutlined";
import NotificationsOutlinedIcon from "@mui/icons-material/NotificationsOutlined";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import OpenInNewIcon from "@mui/icons-material/OpenInNewOutlined";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  Link,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { fetchLatestExtraction, fetchRequirements, type LlmModel, type Requirement, runExtraction, runStructuring } from "@/api/analysis";
import type { NoticeDetail } from "@/api/notices";
import { followOrg } from "@/api/classification";
import { BID_STATUS_LABELS, EXTRA_FIELD_LABELS, fetchNeighbors, fetchNoticeDetail, formatExtraValue } from "@/api/notices";

const DOC_KIND_LABEL: Record<string, string> = { pdf: "PDF", hwpx: "HWPX", hwp: "HWP", other: "기타" };
const EXTRACT_STATUS_LABEL: Record<string, string> = { running: "진행 중", done: "완료", failed: "실패" };

export function NoticeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const noticeId = Number(id);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const detailQuery = useQuery({
    queryKey: ["notice", noticeId],
    queryFn: () => fetchNoticeDetail(noticeId),
  });

  // 이전/다음이 목록의 필터·정렬 순서를 이어서 이동(S1-d) — 카드에서 넘어올 때 붙여온
  // 쿼리스트링을 그대로 재사용해서 neighbors를 조회한다.
  const neighborsQuery = useQuery({
    queryKey: ["notice-neighbors", noticeId, searchParams.toString()],
    queryFn: () => fetchNeighbors(noticeId, searchParams),
  });

  const followMutation = useMutation({
    mutationFn: () => followOrg(noticeId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notice", noticeId] }),
  });

  const extractionQuery = useQuery({
    queryKey: ["notice-extraction", noticeId],
    queryFn: () => fetchLatestExtraction(noticeId),
  });

  const extractMutation = useMutation({
    mutationFn: () => runExtraction(noticeId),
    onSuccess: (result) => queryClient.setQueryData(["notice-extraction", noticeId], result),
  });

  const requirementsQuery = useQuery({
    queryKey: ["notice-requirements", noticeId],
    queryFn: () => fetchRequirements(noticeId),
  });

  const structureMutation = useMutation({
    mutationFn: (model: LlmModel) => runStructuring(noticeId, model),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notice-requirements", noticeId] }),
  });

  if (detailQuery.isLoading) {
    return (
      <Stack alignItems="center" sx={{ py: 8 }}>
        <CircularProgress />
      </Stack>
    );
  }

  if (!detailQuery.data) {
    return <Typography>공고를 찾을 수 없습니다.</Typography>;
  }

  const notice = detailQuery.data;
  const qs = searchParams.toString();

  return (
    <Stack spacing={3} sx={{ maxWidth: 860 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Button component={RouterLink} to={`/notices?${qs}`} size="small">
          ← 목록으로
        </Button>
        <Stack direction="row" spacing={1} alignItems="center">
          <Tooltip title="이전 (현재 필터·정렬 기준)">
            <span>
              <IconButton
                size="small"
                disabled={!neighborsQuery.data?.prev_id}
                onClick={() => navigate(`/notices/${neighborsQuery.data?.prev_id}?${qs}`)}
              >
                <ArrowBackIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="다음 (현재 필터·정렬 기준)">
            <span>
              <IconButton
                size="small"
                disabled={!neighborsQuery.data?.next_id}
                onClick={() => navigate(`/notices/${neighborsQuery.data?.next_id}?${qs}`)}
              >
                <ArrowForwardIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </Stack>

      <Card sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" useFlexGap>
            <Box>
              <Stack direction="row" spacing={0.75} sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
                <Chip label={notice.stage} size="small" color="secondary" variant="outlined" />
                <Chip
                  label={BID_STATUS_LABELS[notice.bid_status]}
                  size="small"
                  color={notice.bid_status === "in_progress" ? "success" : "default"}
                  variant="outlined"
                />
                {notice.biz_type && <Chip label={notice.biz_type} size="small" variant="outlined" />}
                {notice.work_type && <Chip label={notice.work_type} size="small" variant="outlined" />}
              </Stack>
              <Typography variant="h2">{notice.title}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                {notice.org_name ?? "발주기관 미상"} · {notice.region ?? "지역 미상"}
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} alignItems="center">
              <Button
                variant="outlined"
                size="small"
                startIcon={<OpenInNewIcon fontSize="small" />}
                component={Link}
                href={notice.url}
                target="_blank"
                rel="noreferrer"
              >
                원문 보기
              </Button>
              <Button
                variant={notice.org_followed ? "contained" : "outlined"}
                size="small"
                startIcon={notice.org_followed ? <NotificationsActiveIcon /> : <NotificationsOutlinedIcon />}
                disabled={followMutation.isPending || notice.org_followed}
                onClick={() => followMutation.mutate()}
              >
                {notice.org_followed ? "팔로우 중" : "이 기관 팔로우"}
              </Button>
            </Stack>
          </Stack>

          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
            <Field label="공고번호" value={notice.notice_no ?? "미부여"} />
            <Field label="추정가격" value={notice.est_price ? `${(notice.est_price / 100_000_000).toFixed(1)}억원` : "미공개"} />
            <Field label="게시일" value={notice.open_dt ? new Date(notice.open_dt).toLocaleDateString("ko-KR") : "-"} />
            <Field label="마감일" value={notice.close_dt ? new Date(notice.close_dt).toLocaleString("ko-KR") : "마감일 미공개"} />
            {notice.assignee_name && <Field label="담당자" value={notice.assignee_name} />}
          </Stack>

          {notice.scores.length > 0 && (
            <Box>
              <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
                매칭된 관심 분야
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {notice.scores.map((s) => (
                  <Chip key={s.interest_topic_id} label={`${s.name} (+${s.l2_score})`} size="small" />
                ))}
              </Stack>
            </Box>
          )}
        </Stack>
      </Card>

      {notice.requirements.length > 0 && (
        <Card sx={{ p: 3 }}>
          <Typography variant="h3" sx={{ mb: 1.5 }}>
            참여 자격 요건
          </Typography>
          <Stack spacing={1}>
            {notice.requirements.map((req) => (
              <Stack
                key={req.id}
                direction="row"
                spacing={1.5}
                sx={{
                  p: 1,
                  borderRadius: 1,
                  bgcolor: req.we_qualify === false ? "error.lighter" : "transparent",
                }}
              >
                <Chip label={req.type} size="small" />
                <Typography
                  variant="body2"
                  sx={{ color: req.we_qualify === false ? "error.main" : "text.primary", fontWeight: req.we_qualify === false ? 600 : 400 }}
                >
                  {req.value}
                  {req.we_qualify === false && " — 미충족"}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </Card>
      )}

      {notice.extra && Object.keys(notice.extra).length > 0 && (
        <Card sx={{ p: 3 }}>
          <Typography variant="h3" sx={{ mb: 1.5 }}>
            추가 정보
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
            이 소스가 제공하는 원본 필드 그대로입니다 — 목록 응답에 담당자 개인정보는 없습니다.
          </Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2 }}>
            {Object.entries(notice.extra).map(([key, value]) => (
              <Box key={key} sx={{ minWidth: 0 }}>
                <Typography variant="caption" color="text.secondary">
                  {EXTRA_FIELD_LABELS[key] ?? key}
                </Typography>
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                  {formatExtraValue(key, value)}
                </Typography>
              </Box>
            ))}
          </Box>
        </Card>
      )}

      <Divider />

      <ExtractionCard noticeId={noticeId} noticeUrl={notice.url} extractionQuery={extractionQuery} extractMutation={extractMutation} />

      <RequirementsCard
        notice={notice}
        extractionStatus={extractionQuery.data?.status}
        requirementsQuery={requirementsQuery}
        structureMutation={structureMutation}
      />
    </Stack>
  );
}

function ExtractionCard({
  noticeUrl,
  extractionQuery,
  extractMutation,
}: {
  noticeId: number;
  noticeUrl: string;
  extractionQuery: ReturnType<typeof useQuery<Awaited<ReturnType<typeof fetchLatestExtraction>>>>;
  extractMutation: ReturnType<typeof useMutation<Awaited<ReturnType<typeof runExtraction>>, unknown, void>>;
}) {
  const isIris = noticeUrl.includes("iris.go.kr");
  const result = extractMutation.data ?? extractionQuery.data;

  const errorDetail = (extractMutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;

  return (
    <Card sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
        <Box>
          <Typography variant="h3">심층 분석 (파일럿)</Typography>
          <Typography variant="caption" color="text.secondary">
            첨부문서를 다운로드해 텍스트만 추출합니다 — 충족 여부 판정은 아직 하지 않습니다. 지금은 IRIS 공고만 지원.
          </Typography>
        </Box>
        <Tooltip title={isIris ? "" : "이 파일럿은 아직 IRIS 공고만 지원합니다"}>
          <span>
            <Button
              variant="contained"
              size="small"
              startIcon={<AutoAwesomeOutlinedIcon />}
              disabled={!isIris || extractMutation.isPending || result?.status === "running"}
              onClick={() => extractMutation.mutate()}
            >
              {extractMutation.isPending ? "추출 중..." : result ? "다시 추출" : "첨부문서 추출 실행"}
            </Button>
          </span>
        </Tooltip>
      </Stack>

      {errorDetail && (
        <Alert severity="error" sx={{ mb: 1.5 }}>
          {errorDetail}
        </Alert>
      )}

      {result && (
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              label={EXTRACT_STATUS_LABEL[result.status] ?? result.status}
              size="small"
              color={result.status === "done" ? "success" : result.status === "failed" ? "error" : "default"}
            />
            <Typography variant="body2" color="text.secondary">
              {result.docs.length > 0 ? `첨부 ${result.docs.length}건` : "첨부문서 없음"}
            </Typography>
          </Stack>

          {result.docs.map((doc, i) => (
            <Accordion key={`${doc.name}-${i}`} disableGutters variant="outlined">
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0, width: "100%" }}>
                  {doc.extract_ok ? (
                    <CheckCircleOutlineIcon fontSize="small" color="success" />
                  ) : (
                    <ErrorOutlineIcon fontSize="small" color="error" />
                  )}
                  <Chip label={DOC_KIND_LABEL[doc.kind] ?? doc.kind} size="small" />
                  <Typography variant="body2" noWrap sx={{ flex: 1 }}>
                    {doc.name}
                  </Typography>
                  {doc.extract_method && (
                    <Typography variant="caption" color="text.secondary">
                      {doc.extract_method}
                    </Typography>
                  )}
                </Stack>
              </AccordionSummary>
              <AccordionDetails>
                {doc.error && (
                  <Alert severity={doc.extract_ok ? "warning" : "error"} sx={{ mb: 1 }}>
                    {doc.error}
                  </Alert>
                )}
                {doc.text && (
                  <Box
                    sx={{
                      whiteSpace: "pre-wrap",
                      maxHeight: 400,
                      overflow: "auto",
                      p: 1.5,
                      bgcolor: "background.default",
                      borderRadius: 1,
                      fontSize: "0.8125rem",
                    }}
                  >
                    {doc.text}
                  </Box>
                )}
              </AccordionDetails>
            </Accordion>
          ))}
        </Stack>
      )}
    </Card>
  );
}

const OP_LABEL: Record<string, string> = { gte: "이상", lte: "이하", eq: "일치", contains: "포함", manual: "서술형" };
const MODEL_LABEL: Record<LlmModel, string> = { haiku: "Haiku (저렴)", sonnet: "Sonnet", opus: "Opus" };
// 신청자격("자격")과 평가 관련 규칙은 각각 전용 섹션(신청자격·평가기준)에서 다루므로, 나머지
// 요구사양만 분류별로 묶어 보여준다 — 같은 내용이 두 번 나오지 않게.
const OTHER_CATEGORY_ORDER = ["성능", "인증", "실적", "인력", "기타"];

function requirementValueLabel(req: Requirement): string {
  return req.req_value ? `${req.req_value}${req.req_unit ?? ""} ${OP_LABEL[req.op]}` : OP_LABEL[req.op];
}

function RequirementsTable({ requirements }: { requirements: Requirement[] }) {
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>요구사항</TableCell>
          <TableCell>기준값</TableCell>
          <TableCell>조문 위치</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {requirements.map((req, i) => (
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
  );
}

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <Typography variant="subtitle2" fontWeight={700} sx={{ mt: 3, mb: 1 }}>
      {children}
    </Typography>
  );
}

function RequirementsCard({
  notice,
  extractionStatus,
  requirementsQuery,
  structureMutation,
}: {
  notice: NoticeDetail;
  extractionStatus?: string;
  requirementsQuery: ReturnType<typeof useQuery<Awaited<ReturnType<typeof fetchRequirements>>>>;
  structureMutation: ReturnType<typeof useMutation<Awaited<ReturnType<typeof runStructuring>>, unknown, LlmModel>>;
}) {
  const [model, setModel] = useState<LlmModel>("haiku");
  const canRun = extractionStatus === "done";
  const data = requirementsQuery.data;
  const summary = data?.summary;
  const requirements = data?.requirements ?? [];
  const eligibility = requirements.filter((r) => r.category === "자격");
  const otherByCategory = OTHER_CATEGORY_ORDER.map((category) => ({
    category,
    items: requirements.filter((r) => r.category === category),
  })).filter((g) => g.items.length > 0);
  const alreadyStructured = data?.step === "A2_structure";
  const errorDetail = (structureMutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;

  return (
    <Card sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
        <Box>
          <Typography variant="h3">심층 분석 종합 (LLM, 파일럿)</Typography>
          <Typography variant="caption" color="text.secondary">
            규격서에서 사업 내용·요구사양을 추출·정리만 합니다 — 충족 여부 판정은 아직 하지 않습니다. LLM 호출 비용이 발생하므로 신중히 실행하세요.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            size="small"
            select
            label="모델"
            value={model}
            onChange={(e) => setModel(e.target.value as LlmModel)}
            sx={{ minWidth: 140 }}
            disabled={alreadyStructured}
          >
            {(Object.entries(MODEL_LABEL) as [LlmModel, string][]).map(([value, label]) => (
              <MenuItem key={value} value={value}>
                {label}
              </MenuItem>
            ))}
          </TextField>
          <Tooltip title={canRun ? "" : "먼저 위 첨부문서 추출(A1)이 완료돼야 합니다"}>
            <span>
              <Button
                variant="contained"
                size="small"
                disabled={!canRun || alreadyStructured || structureMutation.isPending}
                onClick={() => structureMutation.mutate(model)}
              >
                {structureMutation.isPending ? "구조화 중..." : alreadyStructured ? "구조화 완료됨" : "구조화 실행"}
              </Button>
            </span>
          </Tooltip>
        </Stack>
      </Stack>

      {errorDetail && (
        <Alert severity="error" sx={{ mb: 1.5 }}>
          {errorDetail}
        </Alert>
      )}

      {summary && (
        <>
          <SectionHeading>1. 사업개요</SectionHeading>
          <Table size="small">
            <TableBody>
              <TableRow>
                <TableCell sx={{ width: 140, color: "text.secondary" }}>사업명</TableCell>
                <TableCell>{notice.title}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ color: "text.secondary" }}>발주기관</TableCell>
                <TableCell>{notice.org_name ?? "미상"}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ color: "text.secondary" }}>사업목적</TableCell>
                <TableCell>{summary.purpose}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ color: "text.secondary" }}>사업기간</TableCell>
                <TableCell>{summary.project_period}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ color: "text.secondary" }}>사업금액</TableCell>
                <TableCell>{summary.project_budget}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ color: "text.secondary" }}>입찰(접수)기간</TableCell>
                <TableCell>
                  {notice.open_dt ? new Date(notice.open_dt).toLocaleDateString("ko-KR") : "미상"} ~{" "}
                  {notice.close_dt ? new Date(notice.close_dt).toLocaleString("ko-KR") : "미상"}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>

          {summary.content_items.length > 0 && (
            <>
              <SectionHeading>2. 사업내용</SectionHeading>
              <Table size="small">
                <TableBody>
                  {summary.content_items.map((c, i) => (
                    <TableRow key={i}>
                      <TableCell sx={{ width: 220, verticalAlign: "top", fontWeight: 600 }}>
                        ({`사업${i + 1}`}) {c.title}
                      </TableCell>
                      <TableCell>{c.summary}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}

          <SectionHeading>3. 사업비 조건 (중소기업 기준)</SectionHeading>
          <Table size="small">
            <TableBody>
              <TableRow>
                <TableCell sx={{ width: 220, color: "text.secondary" }}>정부지원금 비율</TableCell>
                <TableCell>{summary.budget_conditions.government_support_ratio}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ color: "text.secondary" }}>기관현금부담 비율</TableCell>
                <TableCell>{summary.budget_conditions.institution_cash_burden_ratio}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ color: "text.secondary" }}>기술료 징수 여부</TableCell>
                <TableCell>{summary.budget_conditions.tech_fee_collection}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ color: "text.secondary" }}>청년인력 조건</TableCell>
                <TableCell>{summary.budget_conditions.youth_hiring_requirement}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell sx={{ color: "text.secondary" }}>인건비 계상 기준</TableCell>
                <TableCell>{summary.budget_conditions.labor_cost_basis}</TableCell>
              </TableRow>
            </TableBody>
          </Table>

          {eligibility.length > 0 && (
            <>
              <SectionHeading>4. 신청자격</SectionHeading>
              <RequirementsTable requirements={eligibility} />
            </>
          )}

          {summary.evaluation.length > 0 && (
            <>
              <SectionHeading>5. 평가기준</SectionHeading>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>항목</TableCell>
                    <TableCell>배점</TableCell>
                    <TableCell>세부 내용</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {summary.evaluation.map((e, i) => (
                    <TableRow key={i}>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>{e.item}</TableCell>
                      <TableCell className="tnum">{e.weight}</TableCell>
                      <TableCell>{e.note}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}

          {otherByCategory.map(({ category, items }) => (
            <Box key={category}>
              <SectionHeading>기타 요구사양 — {category}</SectionHeading>
              <RequirementsTable requirements={items} />
            </Box>
          ))}
        </>
      )}
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" className="tnum" fontWeight={600}>
        {value}
      </Typography>
    </Box>
  );
}
