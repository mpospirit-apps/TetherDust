import { apiFetch } from "./client";
import type { Paginated } from "./admin";

export interface MCPServer {
  id: string;
  name: string;
  description: string;
  url: string;
  transport: string;
  headers: Record<string, unknown>;
  command: string;
  args: unknown[];
  is_active: boolean;
  is_builtin: boolean;
  is_local: boolean;
  has_auth_token: boolean;
  has_command_env: boolean;
  tool_count: number;
  created_at: string;
  updated_at: string;
}

export interface MCPServerInput {
  name: string;
  description?: string;
  url?: string;
  transport?: string;
  headers?: Record<string, unknown>;
  command?: string;
  args?: unknown[];
  auth_token?: string;
  command_env?: string;
  is_active?: boolean;
}

export interface MCPTool {
  id: string;
  tool_name: string;
  display_name: string;
  category: string;
  category_label: string;
  is_enabled: boolean;
  description: string;
}

export interface MCPProbeResult {
  ok?: boolean;
  error?: string;
  url?: string;
  transport?: string;
  has_auth_token?: boolean;
  header_keys?: string[];
  initialize?: {
    status_code?: number;
    elapsed_ms?: number;
    protocol_version?: string;
    server_name?: string;
    server_version?: string;
    body_preview?: string;
  };
  tools_list?: {
    status_code?: number;
    elapsed_ms?: number;
    count?: number;
    tools?: { name: string; description: string }[];
    body_preview?: string;
  };
}

export interface MCPPrompt {
  id: string;
  mcp_server: string;
  prompt_name: string;
  display_name: string;
  content: string;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface MCPPromptInput {
  mcp_server: string;
  prompt_name: string;
  display_name: string;
  content: string;
  is_enabled?: boolean;
}

const SERVER_BASE = "/api/v1/admin/mcp-servers/";
const PROMPT_BASE = "/api/v1/admin/mcp-prompts/";

export function listMCPServers(): Promise<Paginated<MCPServer>> {
  return apiFetch(SERVER_BASE);
}
export function getMCPServer(id: string): Promise<MCPServer> {
  return apiFetch(`${SERVER_BASE}${id}/`);
}
export function createMCPServer(data: MCPServerInput): Promise<MCPServer> {
  return apiFetch(SERVER_BASE, { method: "POST", body: JSON.stringify(data) });
}
export function updateMCPServer(id: string, data: MCPServerInput): Promise<MCPServer> {
  return apiFetch(`${SERVER_BASE}${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}
export function deleteMCPServer(id: string): Promise<void> {
  return apiFetch(`${SERVER_BASE}${id}/`, { method: "DELETE" });
}
export function testMCPServer(id: string): Promise<MCPProbeResult> {
  return apiFetch(`${SERVER_BASE}${id}/test/`, { method: "POST" });
}
export function getMCPServerTools(id: string): Promise<{ results: MCPTool[] }> {
  return apiFetch(`${SERVER_BASE}${id}/tools/`);
}

export function listMCPPrompts(serverId: string): Promise<Paginated<MCPPrompt>> {
  return apiFetch(`${PROMPT_BASE}?mcp_server=${encodeURIComponent(serverId)}`);
}
export function createMCPPrompt(data: MCPPromptInput): Promise<MCPPrompt> {
  return apiFetch(PROMPT_BASE, { method: "POST", body: JSON.stringify(data) });
}
export function updateMCPPrompt(id: string, data: MCPPromptInput): Promise<MCPPrompt> {
  return apiFetch(`${PROMPT_BASE}${id}/`, { method: "PATCH", body: JSON.stringify(data) });
}
export function deleteMCPPrompt(id: string): Promise<void> {
  return apiFetch(`${PROMPT_BASE}${id}/`, { method: "DELETE" });
}
export function toggleMCPPrompt(id: string): Promise<MCPPrompt> {
  return apiFetch(`${PROMPT_BASE}${id}/toggle/`, { method: "POST" });
}
