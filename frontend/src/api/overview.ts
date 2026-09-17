import { apiClient } from "@/api/client";

// 관리자 홈 대시보드 3카드(2026-09-12 재설계 — 고객 현황/시스템 현황/공고 데이터).
// 예전 4카드(공고 데이터/등록된 고객/보고서 생성 현황/시스템 현황) 단일 API는 폐기 —
// 카드마다 API를 분리해서(서버 자원 측정이 0.3초 걸려도 나머지 카드까지 안 기다리게).

export interface RecentReport {
  id: number;
  token: string;
  generated_at: string;
  view_count: number;
  customer_name: string;
}

export interface CustomerOverview {
  total_customers: number;
  with_interests: number;
  profile_summarized: number;
  monthly: {
    months: string[]; // ["2026-04", ..., "2026-09"]
    customer_total: number[]; // 월말 기준 누적 고객 수
    reports_generated: number[]; // 그 달에 생성된 보고서 수
    reports_sent: number[]; // 그 달에 발송된 보고서 수
  };
  recent_reports: RecentReport[];
}

export async function fetchCustomerOverview(): Promise<CustomerOverview> {
  const { data } = await apiClient.get<CustomerOverview>("/overview/customers");
  return data;
}

export interface SystemResourceMetric {
  host_percent: number;
  host_used_bytes: number;
  host_total_bytes: number;
  container_used_bytes?: number;
  container_limit_bytes?: number | null;
}

export interface SystemResources {
  available: boolean;
  error?: string;
  cpu?: { cores: number; host_percent: number; container_percent: number };
  memory?: SystemResourceMetric;
  // app_used_bytes: BidRadar 자체 디스크 사용량(pg_database_size — 첨부파일도 DB에 저장되므로
  // 사실상 DB+파일을 전부 포함, 2026-09-12). 도커 이미지·로그·백업 파일은 미포함.
  disk?: { host_percent: number; host_used_bytes: number; host_total_bytes: number; app_used_bytes?: number };
}

export interface LlmUsageBucket {
  calls: number;
  tokens: number;
  cost_usd: number;
}

export interface LlmUsageSummary {
  total_calls: number;
  total_tokens: number;
  total_cost_usd: number;
  breakdown: {
    structure: LlmUsageBucket;
    customer_profile: LlmUsageBucket;
    report_commentary: LlmUsageBucket;
    notice_strategy: LlmUsageBucket;
  };
}

export interface ChannelStatus {
  id: number;
  name: string;
  status: "ok" | "warn" | "fail" | "inactive" | "no_run_yet";
  last_run_at: string | null;
}

export interface SystemOverview {
  resources: SystemResources;
  llm_usage: LlmUsageSummary;
  channels: ChannelStatus[];
}

export async function fetchSystemOverview(): Promise<SystemOverview> {
  const { data } = await apiClient.get<SystemOverview>("/overview/system");
  return data;
}

export interface NoticeSourceDailySeries {
  source_id: number | null; // null = 소스별이 아니라 "전체" 합산 계열
  source_name: string;
  counts: number[]; // 같은 그래프의 dates와 같은 길이·순서
}

export interface NoticeDailyChart {
  dates: string[]; // "YYYY-MM-DD"(KST), 최근 14일
  series: NoticeSourceDailySeries[]; // 소스별 계열 + "전체" 합산 계열(2026-09-12 지시 — 6개 선)
}

export interface NoticeOverview {
  cumulative_daily: NoticeDailyChart; // 그 날짜까지의 러닝토탈(삭제 데이터 제외)
  collected_daily: NoticeDailyChart; // 그 날 신규 수집 건수
}

export async function fetchNoticeOverview(): Promise<NoticeOverview> {
  const { data } = await apiClient.get<NoticeOverview>("/overview/notices");
  return data;
}

// 2026-09-17 — "공고 데이터" 카드에 그래프 2개 추가. 소스별 계열이 없는 단순한 이름표 기반
// 계열이라 NoticeDailyChart(source_id 필수)와는 별도 타입으로 둔다.
export interface DailyNamedSeries {
  name: string;
  counts: number[];
}

export interface DailySeriesChart {
  dates: string[]; // "YYYY-MM-DD"(KST), 최근 14일
  series: DailyNamedSeries[];
}

export async function fetchAiProcessingOverview(): Promise<DailySeriesChart> {
  const { data } = await apiClient.get<DailySeriesChart>("/overview/ai-processing");
  return data;
}

export async function fetchOpsOverview(): Promise<DailySeriesChart> {
  const { data } = await apiClient.get<DailySeriesChart>("/overview/ops");
  return data;
}
