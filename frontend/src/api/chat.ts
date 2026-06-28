import { apiFetch } from "./client";

export interface AgentStatus {
	name: string | null;
	connected: boolean;
}

export interface ChatSessionItem {
	id: string;
	title: string;
	group: string;
	updated_at: string;
	message_count: number;
}

export function getAgentStatus(): Promise<AgentStatus> {
	return apiFetch("/api/v1/agent-status/");
}

export function listChatSessions(): Promise<{ sessions: ChatSessionItem[] }> {
	return apiFetch("/api/v1/chat/sessions/");
}

export function deleteChatSession(id: string): Promise<void> {
	return apiFetch(`/api/v1/chat/sessions/${id}/`, { method: "DELETE" });
}

// `@`-mention doc resource (from the MCP server, role-filtered).
export interface DocResource {
	uri: string;
	source_name: string;
	path: string;
	name: string;
}

// `/`-command prompt (an enabled MCP prompt the user is allowed to use).
export interface ChatPrompt {
	name: string;
	display_name: string;
	content: string;
}

export function searchDocSources(
	q: string,
): Promise<{ resources: DocResource[] }> {
	const qs = q ? `?q=${encodeURIComponent(q)}` : "";
	return apiFetch(`/api/v1/chat/doc-sources/${qs}`);
}

export function listChatPrompts(): Promise<{ prompts: ChatPrompt[] }> {
	return apiFetch("/api/v1/chat/prompts/");
}
