import { apiFetch } from "./client";

// DRF PageNumberPagination envelope.
export interface Paginated<T> {
	count: number;
	next: string | null;
	previous: string | null;
	results: T[];
}

export interface DatabaseConnection {
	id: string;
	name: string;
	description: string;
	engine: string;
	host: string;
	port: number | null;
	database: string;
	username: string;
	connection_string: string;
	extra_options: Record<string, unknown>;
	read_only: boolean;
	is_active: boolean;
	created_at: string;
	updated_at: string;
}

export type DatabaseInput = Partial<
	Omit<DatabaseConnection, "id" | "created_at" | "updated_at">
> & { password?: string };

export interface EngineChoice {
	value: string;
	label: string;
}

export interface EnginesResponse {
	choices: EngineChoice[];
	default_ports: Record<string, number>;
}

export interface TestResult {
	ok: boolean;
	detail: string;
}

const DB_BASE = "/api/v1/admin/databases/";

export function listDatabases(): Promise<Paginated<DatabaseConnection>> {
	return apiFetch(DB_BASE);
}

export function getDatabase(id: string): Promise<DatabaseConnection> {
	return apiFetch(`${DB_BASE}${id}/`);
}

export function createDatabase(
	data: DatabaseInput,
): Promise<DatabaseConnection> {
	return apiFetch(DB_BASE, { method: "POST", body: JSON.stringify(data) });
}

export function updateDatabase(
	id: string,
	data: DatabaseInput,
): Promise<DatabaseConnection> {
	return apiFetch(`${DB_BASE}${id}/`, {
		method: "PATCH",
		body: JSON.stringify(data),
	});
}

export function deleteDatabase(id: string): Promise<void> {
	return apiFetch(`${DB_BASE}${id}/`, { method: "DELETE" });
}

export function testDatabase(id: string): Promise<TestResult> {
	return apiFetch(`${DB_BASE}${id}/test/`, { method: "POST" });
}

export function getEngines(): Promise<EnginesResponse> {
	return apiFetch(`${DB_BASE}engines/`);
}

// ── Settings (key-value) ────────────────────────────────────────────────────

export interface GeneralSettings {
	codex_service_url: string;
	mcp_base_url: string;
	docgen_timeout: number | null;
	doclibgen_timeout: number | null;
	chartgen_timeout: number | null;
	max_row_limit: number | null;
	hot_reload_interval: number | null;
}

export interface SmtpSettings {
	smtp_host: string;
	smtp_port: number | null;
	smtp_username: string;
	smtp_use_tls: boolean;
	smtp_from_email: string;
	email_max_rows: number | null;
	has_password: boolean;
}

export type SmtpSettingsInput = Omit<SmtpSettings, "has_password"> & {
	smtp_password?: string;
};

export function getGeneralSettings(): Promise<GeneralSettings> {
	return apiFetch("/api/v1/admin/settings/general/");
}

export function updateGeneralSettings(
	data: GeneralSettings,
): Promise<GeneralSettings> {
	return apiFetch("/api/v1/admin/settings/general/", {
		method: "PUT",
		body: JSON.stringify(data),
	});
}

export function getSmtpSettings(): Promise<SmtpSettings> {
	return apiFetch("/api/v1/admin/settings/smtp/");
}

export function updateSmtpSettings(
	data: SmtpSettingsInput,
): Promise<SmtpSettings> {
	return apiFetch("/api/v1/admin/settings/smtp/", {
		method: "PUT",
		body: JSON.stringify(data),
	});
}

export function testSmtp(): Promise<{ message?: string; error?: string }> {
	return apiFetch("/api/v1/admin/settings/smtp/test/", { method: "POST" });
}

// ── Roles ───────────────────────────────────────────────────────────────────

export interface Role {
	id: string;
	name: string;
	description: string;
	is_active: boolean;
	can_chat: boolean;
	can_view_tethers: boolean;
	can_manage_users: boolean;
	is_admin_role: boolean;
	max_row_limit: number | null;
	allowed_tools: string[];
	allowed_databases: string[];
	allowed_doc_sources: string[];
	allowed_codebases: string[];
	allowed_prompts: string[];
	allowed_mcp_servers: string[];
}

export type RoleInput = Omit<Role, "id">;

export interface GrantOption {
	id: string;
	name: string;
	mcp_server?: string | null;
}

export interface RoleGrants {
	tools: GrantOption[];
	prompts: GrantOption[];
	databases: GrantOption[];
	doc_sources: GrantOption[];
	codebases: GrantOption[];
	mcp_servers: GrantOption[];
}

const ROLE_BASE = "/api/v1/admin/roles/";

export function listRoles(): Promise<Paginated<Role>> {
	return apiFetch(ROLE_BASE);
}
export function getRole(id: string): Promise<Role> {
	return apiFetch(`${ROLE_BASE}${id}/`);
}
export function createRole(data: RoleInput): Promise<Role> {
	return apiFetch(ROLE_BASE, { method: "POST", body: JSON.stringify(data) });
}
export function updateRole(id: string, data: RoleInput): Promise<Role> {
	return apiFetch(`${ROLE_BASE}${id}/`, {
		method: "PUT",
		body: JSON.stringify(data),
	});
}
export function deleteRole(id: string): Promise<void> {
	return apiFetch(`${ROLE_BASE}${id}/`, { method: "DELETE" });
}
export function getRoleGrants(): Promise<RoleGrants> {
	return apiFetch(`${ROLE_BASE}grants/`);
}

// ── Users ───────────────────────────────────────────────────────────────────

export interface AdminUser {
	id: number;
	username: string;
	email: string;
	is_staff: boolean;
	is_superuser: boolean;
	is_active: boolean;
	role: string | null;
	role_name: string | null;
	date_joined: string;
}

export interface UserInput {
	username?: string;
	email?: string;
	password?: string;
	is_active?: boolean;
	role?: string | null;
}

const USER_BASE = "/api/v1/admin/users/";

export function listUsers(): Promise<Paginated<AdminUser>> {
	return apiFetch(USER_BASE);
}
export function getUser(id: number): Promise<AdminUser> {
	return apiFetch(`${USER_BASE}${id}/`);
}
export function createUser(data: UserInput): Promise<AdminUser> {
	return apiFetch(USER_BASE, { method: "POST", body: JSON.stringify(data) });
}
export function updateUser(id: number, data: UserInput): Promise<AdminUser> {
	return apiFetch(`${USER_BASE}${id}/`, {
		method: "PATCH",
		body: JSON.stringify(data),
	});
}
export function deleteUser(id: number): Promise<void> {
	return apiFetch(`${USER_BASE}${id}/`, { method: "DELETE" });
}

// ── Audit & monitoring (read-only) ──────────────────────────────────────────

export interface AuditLogEntry {
	id: string;
	created_at: string;
	user: string | null;
	database: string | null;
	success: boolean;
	row_count: number | null;
	execution_time_ms: number | null;
	query: string;
	error_message: string;
}

export interface SessionSummary {
	id: string;
	title: string;
	user: string | null;
	message_count: number;
	updated_at: string;
}

export interface SessionMessage {
	id: string;
	role: "user" | "assistant" | "system";
	content: string;
	tools_used: string[];
	sources_used: { uri?: string; name?: string }[];
	prompts_used: { name?: string; display_name?: string }[];
	created_at: string;
}

export interface SessionDetail {
	id: string;
	title: string;
	user: string | null;
	created_at: string;
	updated_at: string;
	message_count: number;
	messages: SessionMessage[];
}

export function getAuditLog(): Promise<{ results: AuditLogEntry[] }> {
	return apiFetch("/api/v1/admin/audit/");
}

export function getAuditLogEntry(id: string): Promise<AuditLogEntry> {
	return apiFetch(`/api/v1/admin/audit/${id}/`);
}

export function getSessions(): Promise<{ results: SessionSummary[] }> {
	return apiFetch("/api/v1/admin/sessions/");
}

export function getSession(id: string): Promise<SessionDetail> {
	return apiFetch(`/api/v1/admin/sessions/${id}/`);
}

// ── Agents ──────────────────────────────────────────────────────────────────

export interface AgentAuthInfo {
	email?: string;
	plan?: string;
	expires_at?: string;
}

export interface Agent {
	id: string;
	name: string;
	agent_type: string;
	agent_type_display: string;
	system_prompt: string;
	service_url: string;
	is_active: boolean;
	model: string;
	base_url: string;
	reasoning_effort: string;
	has_api_key: boolean;
	has_auth_token: boolean;
	auth_info: AgentAuthInfo | null;
	created_at: string;
	updated_at: string;
}

export interface DeviceLoginStart {
	login_id: string;
	verification_url: string;
	user_code: string;
}

export interface DeviceLoginStatus {
	status: "pending" | "complete" | "error" | "not_found";
	verification_url?: string;
	user_code?: string;
	error?: string;
}

export interface AgentInput {
	name: string;
	agent_type?: string;
	system_prompt?: string;
	service_url?: string;
	model?: string;
	base_url?: string;
	reasoning_effort?: string;
	api_key?: string;
	oauth_token?: string;
}

export interface AgentTypeOption {
	value: string;
	label: string;
}
export interface AgentTypeCategory {
	title: string;
	types: AgentTypeOption[];
}
export interface AgentTypesMeta {
	categories: AgentTypeCategory[];
	direct_api_types: string[];
	api_key_types: string[];
	auth_token_types: string[];
	reasoning_effort_choices: { value: string; label: string }[];
}

const AGENT_BASE = "/api/v1/admin/agents/";

export function listAgents(): Promise<Paginated<Agent>> {
	return apiFetch(AGENT_BASE);
}
export function getAgent(id: string): Promise<Agent> {
	return apiFetch(`${AGENT_BASE}${id}/`);
}
export function getAgentTypes(): Promise<AgentTypesMeta> {
	return apiFetch(`${AGENT_BASE}types/`);
}
export function getDefaultPrompt(
	agentType: string,
): Promise<{ system_prompt: string }> {
	return apiFetch(
		`${AGENT_BASE}default-prompt/?agent_type=${encodeURIComponent(agentType)}`,
	);
}
export function createAgent(data: AgentInput): Promise<Agent> {
	return apiFetch(AGENT_BASE, { method: "POST", body: JSON.stringify(data) });
}
export function updateAgent(id: string, data: AgentInput): Promise<Agent> {
	return apiFetch(`${AGENT_BASE}${id}/`, {
		method: "PATCH",
		body: JSON.stringify(data),
	});
}
export function deleteAgent(id: string): Promise<void> {
	return apiFetch(`${AGENT_BASE}${id}/`, { method: "DELETE" });
}
export function activateAgent(id: string): Promise<Agent> {
	return apiFetch(`${AGENT_BASE}${id}/activate/`, { method: "POST" });
}
export function startDeviceLogin(id: string): Promise<DeviceLoginStart> {
	return apiFetch(`${AGENT_BASE}${id}/device-login/`, { method: "POST" });
}
export function getDeviceLoginStatus(
	id: string,
	loginId: string,
): Promise<DeviceLoginStatus> {
	return apiFetch(`${AGENT_BASE}${id}/device-login/${loginId}/`);
}
