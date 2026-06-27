import type { Paginated } from "./admin";
import { apiFetch } from "./client";

// ── Public dashboards viewer ──────────────────────────────────────────────────

export interface DashboardSummary {
  id: string;
  name: string;
  description: string;
  chart_count: number;
  auto_refresh: boolean;
  refresh_interval: string | null;
}

export interface ChartView {
  id: string;
  title: string;
  description: string;
  chart_type: string;
  custom_d3_code: string;
  width: number;
  height: number;
  position: number;
  last_refreshed_at: string | null;
}

export interface DashboardDetail {
  id: string;
  name: string;
  description: string;
  auto_refresh: boolean;
  refresh_interval: string | null;
  charts: ChartView[];
}

export interface ChartData {
  columns: string[];
  data: Record<string, unknown>[];
  cached?: boolean;
  refreshed_at?: string | null;
  error?: string;
}

export function getDashboards(): Promise<{ dashboards: DashboardSummary[] }> {
  return apiFetch("/api/v1/dashboards/");
}
export function getDashboard(id: string): Promise<DashboardDetail> {
  return apiFetch(`/api/v1/dashboards/${id}/`);
}
export function getChartData(id: string, refresh = false): Promise<ChartData> {
  return apiFetch(`/api/v1/charts/${id}/data/${refresh ? "?refresh=1" : ""}`);
}

// ── Admin: dashboards ─────────────────────────────────────────────────────────

export interface AdminDashboard {
  id: string;
  name: string;
  description: string;
  is_active: boolean;
  auto_refresh: boolean;
  refresh_interval: string | null;
  allowed_roles: string[];
  chart_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminDashboardInput {
  name?: string;
  description?: string;
  is_active?: boolean;
  auto_refresh?: boolean;
  refresh_interval?: string | null;
  allowed_roles?: string[];
}

const DASH_BASE = "/api/v1/admin/dashboards/";

export function listDashboards(): Promise<Paginated<AdminDashboard>> {
  return apiFetch(DASH_BASE);
}
export function getAdminDashboard(id: string): Promise<AdminDashboard> {
  return apiFetch(`${DASH_BASE}${id}/`);
}
export function createDashboard(data: AdminDashboardInput): Promise<AdminDashboard> {
  return apiFetch(DASH_BASE, { method: "POST", body: JSON.stringify(data) });
}
export function updateDashboard(id: string, data: AdminDashboardInput): Promise<AdminDashboard> {
  return apiFetch(`${DASH_BASE}${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}
export function deleteDashboard(id: string): Promise<void> {
  return apiFetch(`${DASH_BASE}${id}/`, { method: "DELETE" });
}

// ── Admin: charts ─────────────────────────────────────────────────────────────

export interface AdminChart {
  id: string;
  dashboard: string;
  database: string;
  database_name: string;
  title: string;
  description: string;
  sql_query: string;
  custom_d3_code: string;
  chart_type: string;
  width: number;
  height: number;
  position: number;
  is_active: boolean;
  last_error: string;
  last_refreshed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminChartInput {
  dashboard?: string;
  database?: string;
  title?: string;
  description?: string;
  sql_query?: string;
  custom_d3_code?: string;
  width?: number;
  height?: number;
  position?: number;
  is_active?: boolean;
}

export interface PreviewResult {
  columns: string[];
  data: Record<string, unknown>[];
  error?: string;
}

const CHART_BASE = "/api/v1/admin/charts/";

export function listCharts(dashboardId: string): Promise<Paginated<AdminChart>> {
  return apiFetch(`${CHART_BASE}?dashboard=${encodeURIComponent(dashboardId)}`);
}
export function getChart(id: string): Promise<AdminChart> {
  return apiFetch(`${CHART_BASE}${id}/`);
}
export function createChart(data: AdminChartInput): Promise<AdminChart> {
  return apiFetch(CHART_BASE, { method: "POST", body: JSON.stringify(data) });
}
export function updateChart(id: string, data: AdminChartInput): Promise<AdminChart> {
  return apiFetch(`${CHART_BASE}${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}
export function deleteChart(id: string): Promise<void> {
  return apiFetch(`${CHART_BASE}${id}/`, { method: "DELETE" });
}
export function previewChart(database: string, sql_query: string): Promise<PreviewResult> {
  return apiFetch(`${CHART_BASE}preview/`, {
    method: "POST",
    body: JSON.stringify({ database, sql_query }),
  });
}
export function getAdminChartData(id: string, refresh = false): Promise<ChartData> {
  return apiFetch(`${CHART_BASE}${id}/data/${refresh ? "?refresh=1" : ""}`);
}

// ── Admin: AI dashboard generation ────────────────────────────────────────────

export interface DashboardGenOptions {
  databases: { id: string; name: string }[];
  doc_sources: { id: string; name: string }[];
  codebases: { id: string; name: string }[];
  agents: { id: string; name: string; is_active: boolean }[];
  dashboard_types: string[];
}

export interface DashboardGenerateRequest {
  dashboard_name: string;
  dashboard_type: string;
  prompt_override?: string;
  agent: string;
  source_db?: string[];
  source_doc?: string[];
  source_codebase?: string[];
}

export interface DashboardGenStatus {
  id: string;
  status: "running" | "success" | "partial" | "failed";
  execution_time_ms: number | null;
  dashboard_id?: string | null;
  charts_created?: number;
  agent_output?: string;
  error?: string;
  dashboard_name?: string;
}

export interface ChartGenLog {
  id: string;
  status: string;
  dashboard_name: string;
  charts_created: number | null;
  execution_time_ms: number | null;
  error_message: string;
  user: string | null;
  agent: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface ChartGenLogDetail extends ChartGenLog {
  errors: string[];
  source_databases: string[];
  source_docs: string[];
  prompt_used: string;
  agent_output: string;
}

export function getDashboardGenerateOptions(): Promise<DashboardGenOptions> {
  return apiFetch(`${DASH_BASE}generate-options/`);
}
export function startDashboardGenerate(
  data: DashboardGenerateRequest
): Promise<{ log_id: string }> {
  return apiFetch(`${DASH_BASE}generate/`, { method: "POST", body: JSON.stringify(data) });
}

const CHARTGEN_LOG_BASE = "/api/v1/admin/chartgen-logs/";

export function getDashboardGenStatus(logId: string): Promise<DashboardGenStatus> {
  return apiFetch(`${CHARTGEN_LOG_BASE}${logId}/status/`);
}
export function listChartGenLogs(): Promise<Paginated<ChartGenLog>> {
  return apiFetch(CHARTGEN_LOG_BASE);
}
export function getChartGenLog(id: string): Promise<ChartGenLogDetail> {
  return apiFetch(`${CHARTGEN_LOG_BASE}${id}/`);
}
