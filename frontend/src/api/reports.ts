import { apiClient } from "@/api/client";

export interface ReportNoticeItem {
  id: number;
  title: string;
  stage: string;
  org_name: string | null;
  est_price: number | null;
  close_dt: string | null;
  score: number;
}

export interface ReportSummary {
  total: number;
  closing_soon: number;
  top_score: number;
}

export interface GeneratedReport {
  id: number;
  token: string;
  customer_id: number;
  notices: ReportNoticeItem[];
  summary: ReportSummary;
  generated_at: string;
}

export interface ReportListItem {
  id: number;
  token: string;
  generated_at: string;
  summary: ReportSummary;
  view_count: number;
}

export interface PublicReport {
  id: number;
  customer_id: number;
  customer_name: string;
  notices: ReportNoticeItem[];
  summary: ReportSummary;
  generated_at: string;
  view_count: number;
}

export async function generateReport(customerId: number): Promise<GeneratedReport> {
  const { data } = await apiClient.post<GeneratedReport>(`/customers/${customerId}/reports`);
  return data;
}

export async function fetchReports(customerId: number): Promise<ReportListItem[]> {
  const { data } = await apiClient.get<ReportListItem[]>(`/customers/${customerId}/reports`);
  return data;
}

export async function fetchPublicReport(token: string): Promise<PublicReport> {
  const { data } = await apiClient.get<PublicReport>(`/public/reports/${token}`);
  return data;
}
