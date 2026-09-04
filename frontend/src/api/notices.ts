import { apiClient } from "@/api/client";

// notice.extra(소스별 부가 필드, 2026-09-02) 원본 키 → 사람이 읽을 라벨. 카드(NoticeCard)와
// 상세(NoticeDetailPage) 양쪽에서 같이 쓰므로 여기 한 곳에 둔다 — 새 소스가 extra 필드를
// 추가할 때마다 여기만 갱신하면 됨.
export const EXTRA_FIELD_LABELS: Record<string, string> = {
  // IRIS 접수예정
  dDay: "마감 D-day",
  rcveStt: "접수상태코드",
  rcveSttSeNmLst: "접수상태",
  rcveStrDe: "접수시작일",
  sorgnId: "전문기관코드",
  blngGovdSe: "소관부처코드",
  blngGovdSeNm: "소관부처",
  budJuriGovdSe: "예산소관코드",
  pbofrTpSeLst: "공모유형코드",
  pbofrTpSeNmLst: "공모유형",
  // IRIS 공모예고
  bsnsYy: "사업연도",
  bsnsCn: "사업내용",
  bsnsPursCn: "사업목적",
  sprtFildCn: "지원분야",
  sprtMinRsctAm: "지원금액(최소)",
  sprtMxRsctAm: "지원금액(최대)",
  sprtPridSe: "지원기간구분",
  bsnsSpchClSeNm: "사업특성구분",
  // 과학기술정보통신부 사업공고
  deptName: "소관부서",
  // K-water 입찰공고
  cntrctDeptNm: "담당부서",
  ctrmthdCdNm: "계약방법",
  tndrStat: "진행상태",
};

// 원 단위 정수로 오는 금액성 extra 필드는 est_price와 같은 방식(억원/만원)으로 보여준다.
const EXTRA_AMOUNT_KEYS = new Set(["sprtMinRsctAm", "sprtMxRsctAm"]);

export function formatExtraValue(key: string, value: string | number | null): string {
  if (value === null || value === "") return "—";
  if (EXTRA_AMOUNT_KEYS.has(key) && typeof value === "number") {
    const eok = value / 100_000_000;
    return eok >= 1 ? `${eok.toFixed(1)}억원` : `${(value / 10_000).toFixed(0)}만원`;
  }
  return String(value);
}

// 공고 생명주기 상태(2026-09-03, 사용자 설계) — notice.stage(어느 수집 단계에서 왔는가)와는
// 독립된 축. open_dt/close_dt와 "지금"만으로 조회 시점마다 백엔드가 다시 계산한다
// (app/services/notice_query.py compute_bid_status) — 저장된 값이 아니라 stale해지지 않는다.
export type BidStatus = "unscheduled" | "upcoming" | "in_progress" | "closed";

export const BID_STATUS_LABELS: Record<BidStatus, string> = {
  unscheduled: "입찰미정",
  upcoming: "입찰예정",
  in_progress: "입찰접수",
  closed: "입찰마감",
};

// S8 A2 요약정보(2026-09-05) — 파일럿이라 대부분의 공고는 아직 분석 전(null). 목록 조회가
// 이미 저장된 값을 얹어 보여줄 뿐, 이 조회 자체가 새 LLM 호출을 만들지 않는다.
export interface NoticeAnalysisSummary {
  project_period: string;
  project_budget: string;
  purpose: string;
  content_narrative: string;
}

export interface NoticeItem {
  id: number;
  notice_no: string | null;
  title: string;
  stage: string;
  pipeline_stage: string;
  bid_status: BidStatus;
  est_price: number | null;
  region: string | null;
  biz_type: string | null;
  work_type: string | null;
  open_dt: string | null;
  close_dt: string | null;
  url: string;
  assignee_name: string | null;
  // 소스별 부가 필드(2026-09-02) — IRIS 접수예정의 공모유형·소관부처·접수상태·D-day 등.
  // 명명 컬럼에 없는 소스 고유 필드만 여기 들어간다. 다른 소스는 null.
  extra: Record<string, string | number | null> | null;
  org_name: string | null;
  priority: number | null;
  analysis_summary: NoticeAnalysisSummary | null;
}

export interface NoticeListResponse {
  items: NoticeItem[];
  total: number;
  page: number;
  size: number;
  tab: string;
}

export interface FilterOptions {
  topics: { id: number; name: string }[];
  orgs: { id: number; name: string }[];
  sources: { id: number; name: string }[];
  stages: string[];
  regions: string[];
  biz_types: string[];
  work_types: string[];
}

// 2026-09-03 재구성 — stage(어느 소스에서 왔는가) 기준 2분류 대신 bid_status(생명주기) 기준
// 4단계로. "all"만 그대로 유지.
export type NoticeTab = "all" | BidStatus;
export type NoticeSort = "priority" | "close_asc" | "open_desc" | "price_desc" | "price_asc";

export async function fetchNotices(params: URLSearchParams): Promise<NoticeListResponse> {
  const { data } = await apiClient.get<NoticeListResponse>("/notices", { params });
  return data;
}

export async function fetchNoticeCounts(): Promise<Record<NoticeTab, number>> {
  const { data } = await apiClient.get<Record<NoticeTab, number>>("/notices/counts");
  return data;
}

export async function fetchFilterOptions(): Promise<FilterOptions> {
  const { data } = await apiClient.get<FilterOptions>("/notices/filter-options");
  return data;
}

export interface NoticeScore {
  interest_topic_id: number;
  name: string;
  l2_score: number;
  reason: string | null;
}

export interface Requirement {
  id: number;
  type: string;
  value: string;
  we_qualify: boolean | null;
}

export interface NoticeDetail {
  id: number;
  notice_no: string | null;
  title: string;
  stage: string;
  pipeline_stage: string;
  bid_status: BidStatus;
  est_price: number | null;
  region: string | null;
  biz_type: string | null;
  work_type: string | null;
  open_dt: string | null;
  close_dt: string | null;
  url: string;
  assignee_name: string | null;
  extra: Record<string, string | number | null> | null;
  org_id: number | null;
  org_name: string | null;
  scores: NoticeScore[];
  requirements: Requirement[];
  org_followed: boolean;
}

export async function fetchNoticeDetail(id: number): Promise<NoticeDetail> {
  const { data } = await apiClient.get<NoticeDetail>(`/notices/${id}`);
  return data;
}

export async function fetchNeighbors(
  id: number,
  params: URLSearchParams,
): Promise<{ prev_id: number | null; next_id: number | null }> {
  const { data } = await apiClient.get(`/notices/${id}/neighbors`, { params });
  return data;
}
