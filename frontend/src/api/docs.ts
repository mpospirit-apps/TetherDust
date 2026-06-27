import type { Paginated } from "./admin";
import { apiFetch } from "./client";

// ── Public docs viewer ───────────────────────────────────────────────────────

export interface DocTreeNode {
  name: string;
  path: string;
  type: "file" | "dir";
  children?: DocTreeNode[];
  is_code?: boolean;
}

export interface DocSourceTree {
  id: string;
  name: string;
  doc_type: string;
  tree: DocTreeNode[];
}

export interface DocContent {
  source: string;
  path: string;
  title: string;
  is_markdown: boolean;
  language: string;
  content: string;
}

export function getDocSources(): Promise<{ sources: DocSourceTree[] }> {
  return apiFetch("/api/v1/docs/sources/");
}

export function getDocContent(source: string, path: string): Promise<DocContent> {
  const qs = new URLSearchParams({ source, path });
  return apiFetch(`/api/v1/docs/content/?${qs.toString()}`);
}

// ── Admin doc-source management ───────────────────────────────────────────────

export interface DocSource {
  id: string;
  folder_name: string;
  doc_type: string;
  doc_type_display: string;
  description: string;
  file_patterns: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DocSourceInput {
  folder_name?: string;
  doc_type?: string;
  description?: string;
  file_patterns?: string[];
  is_active?: boolean;
}

export interface DocSourceValidation {
  ok: boolean;
  level: "success" | "warning" | "error";
  message: string;
  file_count?: number;
  last_modified?: string;
}

export interface FolderOption {
  name: string;
  registered: boolean;
}

export interface DocTypeOption {
  value: string;
  label: string;
  description?: string;
}

export interface GenerateOptions {
  databases: { id: string; name: string }[];
  doc_sources: { id: string; name: string }[];
  codebases: { id: string; name: string }[];
  agents: { id: string; name: string; is_active: boolean }[];
  dest_folders: string[];
  top_folders: string[];
  doc_types: DocTypeOption[];
  library_doc_types: DocTypeOption[];
}

export interface GenerateRequest {
  doc_name: string;
  doc_type: string;
  destination: string;
  scope?: string;
  agent: string;
  source_db?: string[];
  source_doc?: string[];
  source_codebase?: string[];
}

export interface LibraryRequest {
  library_name: string;
  source_doc_type: string;
  agent: string;
  source_db?: string[];
  source_doc?: string[];
  source_codebase?: string[];
}

export interface DocGenStatus {
  id: string;
  status: "running" | "success" | "partial" | "failed";
  execution_time_ms: number | null;
  is_library: boolean;
  // single-file, running
  file_exists?: boolean;
  agent_output?: string;
  // failed
  error?: string;
  // done (single)
  folder?: string;
  file_count?: number;
  content?: string;
  file_size?: number | null;
  warnings?: string[];
  // done (library)
  files?: { path: string; size: number }[];
  total_size?: number;
}

export interface DocGenLog {
  id: string;
  status: string;
  destination: string;
  filename: string;
  doc_type: string;
  is_library: boolean;
  execution_time_ms: number | null;
  file_size: number | null;
  error_message: string;
  user: string | null;
  agent: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface DocGenLogDetail extends DocGenLog {
  errors: { database?: string; error?: string }[];
  source_databases: string[];
  source_docs: string[];
  prompt_used: string;
  agent_output: string;
}

const BASE = "/api/v1/admin/docsources/";

export function listDocSources(): Promise<Paginated<DocSource>> {
  return apiFetch(BASE);
}
export function getDocSource(id: string): Promise<DocSource> {
  return apiFetch(`${BASE}${id}/`);
}
export function createDocSource(data: DocSourceInput): Promise<DocSource> {
  return apiFetch(BASE, { method: "POST", body: JSON.stringify(data) });
}
export function updateDocSource(id: string, data: DocSourceInput): Promise<DocSource> {
  return apiFetch(`${BASE}${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}
export function deleteDocSource(id: string): Promise<void> {
  return apiFetch(`${BASE}${id}/`, { method: "DELETE" });
}
export function validateDocSource(id: string): Promise<DocSourceValidation> {
  return apiFetch(`${BASE}${id}/validate/`, { method: "POST" });
}
export function getDocSourceFolders(): Promise<{ folders: FolderOption[] }> {
  return apiFetch(`${BASE}folders/`);
}
export function getGenerateOptions(): Promise<GenerateOptions> {
  return apiFetch(`${BASE}generate-options/`);
}
export function startGenerate(data: GenerateRequest): Promise<{ log_id: string }> {
  return apiFetch(`${BASE}generate/`, { method: "POST", body: JSON.stringify(data) });
}
export function startGenerateLibrary(data: LibraryRequest): Promise<{ log_id: string }> {
  return apiFetch(`${BASE}generate-library/`, { method: "POST", body: JSON.stringify(data) });
}

const LOG_BASE = "/api/v1/admin/docgen-logs/";

export function getDocGenStatus(logId: string): Promise<DocGenStatus> {
  return apiFetch(`${LOG_BASE}${logId}/status/`);
}
export function listDocGenLogs(): Promise<Paginated<DocGenLog>> {
  return apiFetch(LOG_BASE);
}
export function getDocGenLog(id: string): Promise<DocGenLogDetail> {
  return apiFetch(`${LOG_BASE}${id}/`);
}
