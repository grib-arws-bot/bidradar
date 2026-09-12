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

export interface NoticeCumulativeDailyPoint {
  date: string; // "YYYY-MM-DD"(KST)
  total: number; // 그 날짜까지의 전체 소스 누적 총량(러닝토탈)
}

export interface NoticeSourceDailySeries {
  source_id: number;
  source_name: string;
  counts: number[]; // NoticeOverview.collected_daily.dates와 같은 길이·순서
}

export interface NoticeOverview {
  cumulative_daily: NoticeCumulativeDailyPoint[]; // 최근 14일, 선 그래프 1개
  collected_daily: { dates: string[]; series: NoticeSourceDailySeries[] }; // 소스별 선 그래프 여러 개
}

export async function fetchNoticeOverview(): Promise<NoticeOverview> {
  const { data } = await apiClient.get<NoticeOverview>("/overview/notices");
  return data;
}
