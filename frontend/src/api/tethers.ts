import type { Paginated } from "./admin";
import { apiFetch } from "./client";
import type { TetherGraph } from "../tethers/types";

// ── Public tethers viewer ─────────────────────────────────────────────────────

export interface TetherSummary {
  id: string;
  name: string;
  description: string;
  source_name: string;
  database_name: string;
  has_graph: boolean;
}

export interface TetherDetail extends TetherSummary {
  status: string | null;
}

export function getTethers(): Promise<{ tethers: TetherSummary[] }> {
  return apiFetch("/api/v1/tethers/");
}
export function getTether(id: string): Promise<TetherDetail> {
  return apiFetch(`/api/v1/tethers/${id}/`);
}
export function getTetherGraph(id: string): Promise<TetherGraph> {
  return apiFetch(`/api/v1/tethers/${id}/graph/`);
}

// ── Admin: codebases ──────────────────────────────────────────────────────────

export type SyncStatus = "pending" | "syncing" | "ok" | "error";

export interface Codebase {
  id: string;
  name: string;
  description: string;
  provider: string;
  repo_url: string;
  branch: string;
  subpath: string;
  include_globs: string[];
  exclude_globs: string[];
  has_token: boolean;
  is_active: boolean;
  sync_status: SyncStatus;
  sync_error: string;
  last_synced_at: string | null;
  default_branch: string;
  created_at: string;
  updated_at: string;
}

export interface CodebaseInput {
  name?: string;
  description?: string;
  provider?: string;
  repo_url?: string;
  branch?: string;
  subpath?: string;
  include_globs?: string[];
  exclude_globs?: string[];
  access_token?: string;
  is_active?: boolean;
}

const CB_BASE = "/api/v1/admin/codebases/";

export function listCodebases(): Promise<Paginated<Codebase>> {
  return apiFetch(CB_BASE);
}
export function getCodebase(id: string): Promise<Codebase> {
  return apiFetch(`${CB_BASE}${id}/`);
}
export function createCodebase(data: CodebaseInput): Promise<Codebase> {
  return apiFetch(CB_BASE, { method: "POST", body: JSON.stringify(data) });
}
export function updateCodebase(id: string, data: CodebaseInput): Promise<Codebase> {
  return apiFetch(`${CB_BASE}${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}
export function deleteCodebase(id: string): Promise<void> {
  return apiFetch(`${CB_BASE}${id}/`, { method: "DELETE" });
}
export function syncCodebase(id: string): Promise<{ sync_status: SyncStatus }> {
  return apiFetch(`${CB_BASE}${id}/sync/`, { method: "POST" });
}

// ── Admin: tethers ────────────────────────────────────────────────────────────

export interface LatestTetherVersion {
  id: string;
  version_number: number;
  status: string;
  started_at: string;
}

export interface AdminTether {
  id: string;
  name: string;
  description: string;
  codebase: string | null;
  codebase_doc_source: string | null;
  database_doc_source: string;
  source_name: string;
  database_name: string;
  current_status: string | null;
  latest_version: LatestTetherVersion | null;
  is_active: boolean;
  allowed_roles: string[];
  created_at: string;
  updated_at: string;
}

export interface AdminTetherInput {
  name?: string;
  description?: string;
  codebase?: string | null;
  codebase_doc_source?: string | null;
  database_doc_source?: string;
  is_active?: boolean;
  allowed_roles?: string[];
}

export interface TetherVersionRow {
  id: string;
  version_number: number;
  status: string;
  started_at: string;
  completed_at: string | null;
  execution_time_ms: number | null;
  error_message: string;
  agent_log_excerpt: string;
  triggered_by: string | null;
  is_current: boolean;
}

export interface TetherStatus {
  status: string;
  version_number?: number;
  version_id?: string;
  agent_output?: string;
  error?: string;
  execution_time_ms?: number | null;
  is_current?: boolean;
}

export interface TetherSources {
  codebases: { id: string; name: string }[];
  codebase_docs: { id: string; name: string }[];
  database_docs: { id: string; name: string }[];
}

const TTH_BASE = "/api/v1/admin/tethers/";

export function listTethers(): Promise<Paginated<AdminTether>> {
  return apiFetch(TTH_BASE);
}
export function getAdminTether(id: string): Promise<AdminTether> {
  return apiFetch(`${TTH_BASE}${id}/`);
}
export function createTether(data: AdminTetherInput): Promise<AdminTether> {
  return apiFetch(TTH_BASE, { method: "POST", body: JSON.stringify(data) });
}
export function updateTether(id: string, data: AdminTetherInput): Promise<AdminTether> {
  return apiFetch(`${TTH_BASE}${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}
export function deleteTether(id: string): Promise<void> {
  return apiFetch(`${TTH_BASE}${id}/`, { method: "DELETE" });
}
export function regenerateTether(id: string): Promise<{ version_id: string; version_number: number }> {
  return apiFetch(`${TTH_BASE}${id}/regenerate/`, { method: "POST" });
}
export function getTetherStatus(id: string): Promise<TetherStatus> {
  return apiFetch(`${TTH_BASE}${id}/status/`);
}
export function getTetherVersions(id: string): Promise<{ versions: TetherVersionRow[] }> {
  return apiFetch(`${TTH_BASE}${id}/versions/`);
}
export function getTetherSources(): Promise<TetherSources> {
  return apiFetch(`${TTH_BASE}sources/`);
}
