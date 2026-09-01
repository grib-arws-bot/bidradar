import { apiClient } from "@/api/client";

export interface NoticeItem {
  id: number;
  notice_no: string | null;
  title: string;
  stage: string;
  pipeline_stage: string;
  est_price: number | null;
  region: string | null;
  biz_type: string | null;
  work_type: string | null;
  open_dt: string | null;
  close_dt: string | null;
  url: string;
  assignee_name: string | null;
  org_name: string | null;
  priority: number | null;
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

export type NoticeTab = "all" | "pre_stage" | "bid_stage";
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
  est_price: number | null;
  region: string | null;
  biz_type: string | null;
  work_type: string | null;
  open_dt: string | null;
  close_dt: string | null;
  url: string;
  assignee_name: string | null;
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
