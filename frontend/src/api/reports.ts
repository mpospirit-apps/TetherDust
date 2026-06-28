import type { Paginated } from "./admin";
import { apiFetch } from "./client";

// ── Shared execution shape ────────────────────────────────────────────────────

export interface ExecutionResult {
	id: string;
	status: "running" | "success" | "failed";
	row_count: number | null;
	execution_time_ms: number | null;
	started_at: string;
	completed_at: string | null;
	error_message: string;
	column_names: string[];
	rows: unknown[][];
	preview_limit: number;
}

// ── Public reports viewer ─────────────────────────────────────────────────────

export interface LatestRun {
	id: string;
	status: "running" | "success" | "failed";
	started_at: string;
	row_count: number | null;
	execution_time_ms: number | null;
}

export interface ReportListItem {
	id: string;
	name: string;
	description: string;
	database: string;
	latest_run: LatestRun | null;
}

export interface ReportListResponse {
	email_enabled: boolean;
	reports: ReportListItem[];
}

export interface ReportMeta {
	name: string;
	description: string;
}

export interface ReportLatestResponse {
	report: ReportMeta;
	email_enabled: boolean;
	execution: ExecutionResult | null;
}

export interface HistoryEntry {
	id: string;
	status: "running" | "success" | "failed";
	started_at: string;
	execution_time_ms: number | null;
	row_count: number | null;
}

export interface ReportHistoryResponse {
	report: ReportMeta;
	executions: HistoryEntry[];
}

export interface ExecutionDetailResponse {
	report: ReportMeta;
	email_enabled: boolean;
	execution: ExecutionResult;
}

export function getReports(): Promise<ReportListResponse> {
	return apiFetch("/api/v1/reports/");
}
export function getReportLatest(id: string): Promise<ReportLatestResponse> {
	return apiFetch(`/api/v1/reports/${id}/latest/`);
}
export function getReportHistory(id: string): Promise<ReportHistoryResponse> {
	return apiFetch(`/api/v1/reports/${id}/history/`);
}
export function getExecution(id: string): Promise<ExecutionDetailResponse> {
	return apiFetch(`/api/v1/executions/${id}/`);
}
export function executionDownloadUrl(id: string, fmt: "csv" | "excel"): string {
	return `/api/v1/executions/${id}/download/${fmt}/`;
}
export function sendExecutionEmail(id: string): Promise<{ detail: string }> {
	return apiFetch(`/api/v1/executions/${id}/send-email/`, { method: "POST" });
}

// ── Admin: report definitions ─────────────────────────────────────────────────

export type ScheduleType =
	| "manual"
	| "interval"
	| "daily"
	| "weekly"
	| "monthly";
export type DeliveryMethod = "in_app" | "email" | "slack" | "teams";

export interface ReportDefinition {
	id: string;
	name: string;
	description: string;
	database: string;
	database_name: string;
	sql_query: string;
	schedule_type: ScheduleType;
	schedule_interval_minutes: number | null;
	schedule_time: string | null;
	schedule_day_of_week: number | null;
	schedule_day_of_month: number | null;
	next_run_at: string | null;
	delivery_method: DeliveryMethod;
	is_active: boolean;
	allowed_roles: string[];
	email_recipients: string[];
	latest_run: {
		id: string;
		status: string;
		started_at: string;
		row_count: number | null;
	} | null;
	created_at: string;
	updated_at: string;
}

export interface ReportDefinitionInput {
	name?: string;
	description?: string;
	database?: string;
	sql_query?: string;
	schedule_type?: ScheduleType;
	schedule_interval_minutes?: number | null;
	schedule_time?: string | null;
	schedule_day_of_week?: number | null;
	schedule_day_of_month?: number | null;
	delivery_method?: DeliveryMethod;
	is_active?: boolean;
	allowed_roles?: string[];
	email_recipients?: string[];
}

const RPT_BASE = "/api/v1/admin/reports/";

export function listReports(): Promise<Paginated<ReportDefinition>> {
	return apiFetch(RPT_BASE);
}
export function getReportDefinition(id: string): Promise<ReportDefinition> {
	return apiFetch(`${RPT_BASE}${id}/`);
}
export function createReport(
	data: ReportDefinitionInput,
): Promise<ReportDefinition> {
	return apiFetch(RPT_BASE, { method: "POST", body: JSON.stringify(data) });
}
export function updateReport(
	id: string,
	data: ReportDefinitionInput,
): Promise<ReportDefinition> {
	return apiFetch(`${RPT_BASE}${id}/`, {
		method: "PATCH",
		body: JSON.stringify(data),
	});
}
export function deleteReport(id: string): Promise<void> {
	return apiFetch(`${RPT_BASE}${id}/`, { method: "DELETE" });
}
export function runReport(id: string): Promise<ExecutionResult> {
	return apiFetch(`${RPT_BASE}${id}/run/`, { method: "POST" });
}
export function previewReport(id: string): Promise<ExecutionResult> {
	return apiFetch(`${RPT_BASE}${id}/preview/`, { method: "POST" });
}
export function toggleReport(id: string): Promise<{ is_active: boolean }> {
	return apiFetch(`${RPT_BASE}${id}/toggle/`, { method: "POST" });
}

// ── Admin: execution monitor ──────────────────────────────────────────────────

export interface ReportExecutionRow {
	id: string;
	definition: string;
	report_name: string;
	status: "running" | "success" | "failed";
	started_at: string;
	completed_at: string | null;
	execution_time_ms: number | null;
	row_count: number | null;
	error_message: string;
	triggered_by: string | null;
}

const REX_BASE = "/api/v1/admin/report-executions/";

export function listExecutions(
	definitionId?: string,
): Promise<Paginated<ReportExecutionRow>> {
	const qs = definitionId
		? `?definition=${encodeURIComponent(definitionId)}`
		: "";
	return apiFetch(`${REX_BASE}${qs}`);
}
