import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	createMCPPrompt,
	deleteMCPPrompt,
	getMCPServer,
	getMCPServerTools,
	listMCPPrompts,
	type MCPProbeResult,
	type MCPPrompt,
	type MCPTool,
	testMCPServer,
	toggleMCPPrompt,
	updateMCPPrompt,
} from "../../api/mcp";
import { FormCheckbox, FormField } from "../components/forms";

const TOOL_CATEGORY_ICON: Record<string, string> = {
	querying: "fa-database",
	docs: "fa-book",
	charts: "fa-chart-simple",
	codebases: "fa-code",
	// Matches the Tethers nav tab's own icon (see NAV_LINKS in Navbar.tsx).
	tethers: "fa-diagram-project",
	reports: "fa-file-lines",
};
const DEFAULT_TOOL_ICON = "fa-wrench";

// Colors match each category's counterpart nav tab accent (see NAV_LINKS in
// Navbar.tsx: Chat=cyan, Docs=lime, Reports=orange, Dashboards=red,
// Tethers=pink). Querying and Codebases have no nav-tab counterpart of their
// own, so they fall back to the app-wide default icon color (cyan).
const TOOL_CATEGORY_COLOR: Record<string, string> = {
	docs: "var(--c-lime)",
	charts: "var(--c-red)",
	tethers: "var(--c-pink)",
	reports: "var(--c-orange)",
};
const DEFAULT_TOOL_COLOR = "var(--c-cyan)";

// Preserves the API's category ordering (already grouped/sorted server-side)
// instead of re-sorting client-side.
function groupToolsByCategory(
	tools: MCPTool[],
): { category: string; tools: MCPTool[] }[] {
	const groups: { category: string; tools: MCPTool[] }[] = [];
	const byCategory = new Map<string, MCPTool[]>();
	for (const t of tools) {
		let bucket = byCategory.get(t.category_label);
		if (!bucket) {
			bucket = [];
			byCategory.set(t.category_label, bucket);
			groups.push({ category: t.category_label, tools: bucket });
		}
		bucket.push(t);
	}
	return groups;
}

interface PromptForm {
	prompt_name: string;
	display_name: string;
	content: string;
	is_enabled: boolean;
}
const EMPTY_PROMPT: PromptForm = {
	prompt_name: "",
	display_name: "",
	content: "",
	is_enabled: true,
};

function ToolSchema({ tool }: { tool: MCPTool }) {
	if (tool.parameters === undefined) return null;

	return (
		<div className="tool-schema">
			<div className="tool-schema__label">Parameters</div>
			{tool.parameters.length === 0 ? (
				<p>None.</p>
			) : (
				<ul className="tool-schema__params">
					{tool.parameters.map((p) => (
						<li key={p.name} className="tool-schema__param-head">
							<span className="type-badge">{p.type}</span>
							<code style={p.required ? undefined : { color: "var(--c-lime)" }}>
								{p.name}
							</code>
						</li>
					))}
				</ul>
			)}
			{tool.returns && (
				<div className="tool-schema__returns">
					<span className="tool-schema__label">Returns</span>{" "}
					<span className="type-badge">{tool.returns}</span>
				</div>
			)}
		</div>
	);
}

function ProbeReport({ result }: { result: MCPProbeResult }) {
	return (
		<div className="card" style={{ marginTop: "var(--md)" }}>
			<div style={{ marginBottom: "var(--sm)" }}>
				{result.ok ? (
					<span className="badge badge-success">Reachable ✓</span>
				) : (
					<span className="badge badge-error">Failed</span>
				)}
			</div>
			{result.url && (
				<p className="text-sec text-sm">
					Probed <span className="text-mono">{result.url}</span>
					{result.transport ? ` (${result.transport})` : ""}
				</p>
			)}
			{result.error && <p className="text-sec">{result.error}</p>}
			{result.initialize && (
				<p className="text-sec text-sm">
					initialize: HTTP {result.initialize.status_code} in{" "}
					{result.initialize.elapsed_ms}ms
					{result.initialize.server_name
						? ` · ${result.initialize.server_name}`
						: ""}
					{result.initialize.server_version
						? ` v${result.initialize.server_version}`
						: ""}
				</p>
			)}
			{result.tools_list?.count != null && (
				<div>
					<p className="text-sec text-sm">
						tools/list: {result.tools_list.count} tool(s) in{" "}
						{result.tools_list.elapsed_ms}ms
					</p>
					<ul className="text-sm">
						{(result.tools_list.tools ?? []).map((t) => (
							<li key={t.name}>
								<strong>{t.name}</strong>
								{t.description ? ` — ${t.description}` : ""}
							</li>
						))}
					</ul>
				</div>
			)}
		</div>
	);
}

export function MCPServerDetailPage() {
	const { id } = useParams();
	const serverId = id as string;
	const queryClient = useQueryClient();

	const server = useQuery({
		queryKey: ["admin", "mcp-servers", serverId],
		queryFn: () => getMCPServer(serverId),
	});
	const tools = useQuery({
		queryKey: ["admin", "mcp-servers", serverId, "tools"],
		queryFn: () => getMCPServerTools(serverId),
	});
	const prompts = useQuery({
		queryKey: ["admin", "mcp-prompts", serverId],
		queryFn: () => listMCPPrompts(serverId),
	});

	const [probe, setProbe] = useState<MCPProbeResult | null>(null);
	const test = useMutation({
		mutationFn: () => testMCPServer(serverId),
		onSuccess: setProbe,
		onError: (err) =>
			setProbe({
				ok: false,
				error: apiErrorDetail(err, "Test request failed."),
			}),
	});

	// Prompt editor: null = closed, "new" = create, else editing prompt id.
	const [editing, setEditing] = useState<string | null>(null);
	const [promptForm, setPromptForm] = useState<PromptForm>(EMPTY_PROMPT);
	const [promptError, setPromptError] = useState<string | null>(null);

	const invalidatePrompts = () =>
		queryClient.invalidateQueries({
			queryKey: ["admin", "mcp-prompts", serverId],
		});

	const savePrompt = useMutation({
		mutationFn: () => {
			const payload = { ...promptForm, mcp_server: serverId };
			return editing && editing !== "new"
				? updateMCPPrompt(editing, payload)
				: createMCPPrompt(payload);
		},
		onSuccess: () => {
			invalidatePrompts();
			setEditing(null);
			setPromptForm(EMPTY_PROMPT);
		},
		onError: (err) => setPromptError(apiErrorDetail(err, "Save failed.")),
	});
	const removePrompt = useMutation({
		mutationFn: deleteMCPPrompt,
		onSuccess: invalidatePrompts,
		onError: (err) => window.alert(apiErrorDetail(err, "Delete failed.")),
	});
	const toggle = useMutation({
		mutationFn: toggleMCPPrompt,
		onSuccess: invalidatePrompts,
		onError: (err) => window.alert(apiErrorDetail(err, "Toggle failed.")),
	});

	function openNew() {
		setPromptForm(EMPTY_PROMPT);
		setPromptError(null);
		setEditing("new");
	}
	function openEdit(p: MCPPrompt) {
		setPromptForm({
			prompt_name: p.prompt_name,
			display_name: p.display_name,
			content: p.content,
			is_enabled: p.is_enabled,
		});
		setPromptError(null);
		setEditing(p.id);
	}
	function onPromptSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setPromptError(null);
		savePrompt.mutate();
	}

	if (server.isLoading) {
		return (
			<div className="card">
				<p className="text-sec">Loading…</p>
			</div>
		);
	}
	if (server.isError || !server.data) {
		return (
			<div className="card">
				<p className="text-sec">Failed to load server.</p>
			</div>
		);
	}
	const s = server.data;

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>{s.name}</h1>
					<p>{s.description || "MCP server"}</p>
				</div>
				<div className="flex-gap">
					{!s.is_builtin && (
						<Link
							to={`/admin/mcp-servers/${s.id}/edit`}
							className="btn btn-secondary"
						>
							Edit
						</Link>
					)}
					<Link to="/admin/mcp-servers" className="btn btn-ghost">
						Back
					</Link>
				</div>
			</div>

			<div className="card">
				<dl
					style={{
						display: "grid",
						gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
						gap: "var(--md)",
						margin: 0,
					}}
				>
					<div>
						<dt className="text-sec text-sm">Type</dt>
						<dd>
							{s.is_builtin
								? "Built-in"
								: s.is_local
									? "Local (subprocess)"
									: "Remote (HTTP)"}
						</dd>
					</div>
					{s.url && (
						<div>
							<dt className="text-sec text-sm">URL</dt>
							<dd className="text-mono">{s.url}</dd>
						</div>
					)}
					{s.command && (
						<div>
							<dt className="text-sec text-sm">Command</dt>
							<dd className="text-mono">
								{s.command}{" "}
								{Array.isArray(s.args) ? (s.args as string[]).join(" ") : ""}
							</dd>
						</div>
					)}
					<div>
						<dt className="text-sec text-sm">Status</dt>
						<dd>{s.is_active ? "Active" : "Inactive"}</dd>
					</div>
				</dl>
				{!s.is_builtin && (
					<div style={{ marginTop: "var(--md)" }}>
						<button
							type="button"
							className="btn btn-secondary"
							disabled={test.isPending}
							onClick={() => test.mutate()}
						>
							{test.isPending ? "Testing…" : "Test connection"}
						</button>
					</div>
				)}
				{probe && <ProbeReport result={probe} />}
			</div>

			<h2 style={{ marginTop: "var(--lg)" }}>Tools</h2>
			{tools.isLoading ? (
				<div className="card">
					<p className="text-sec">Loading…</p>
				</div>
			) : (tools.data?.results ?? []).length === 0 ? (
				<div className="card">
					<p className="text-sec">No tools registered for this server.</p>
				</div>
			) : (
				groupToolsByCategory(tools.data?.results ?? []).map((group) => (
					<div className="choice-section" key={group.category}>
						<h3 className="choice-section__title">{group.category}</h3>
						<div className="choice-list choice-list--grid">
							{group.tools.map((t) => (
								<div key={t.id} className="choice-card choice-card--static">
									<i
										className={`fa-solid ${TOOL_CATEGORY_ICON[t.category] ?? DEFAULT_TOOL_ICON} choice-card__icon`}
										style={{
											color:
												TOOL_CATEGORY_COLOR[t.category] ?? DEFAULT_TOOL_COLOR,
										}}
									/>
									<div className="choice-card__body">
										<h4>{t.display_name}</h4>
										<p className="text-mono" style={{ marginBottom: 2 }}>
											{t.tool_name}
										</p>
										{t.description && <p>{t.description}</p>}
										<ToolSchema tool={t} />
									</div>
								</div>
							))}
						</div>
					</div>
				))
			)}

			<div
				className="page-header"
				style={{ marginTop: "var(--lg)", marginBottom: "var(--sm)" }}
			>
				<h2 style={{ margin: 0 }}>Prompts</h2>
				{editing === null && (
					<button
						type="button"
						className="btn btn-primary btn-sm"
						onClick={openNew}
					>
						+ Add Prompt
					</button>
				)}
			</div>

			{editing !== null && (
				<form
					onSubmit={onPromptSubmit}
					className="card"
					style={{ marginBottom: "var(--md)" }}
				>
					<h3 style={{ margin: "0 0 var(--md)" }}>
						{editing === "new" ? "New Prompt" : "Edit Prompt"}
					</h3>
					{promptError && (
						<div
							className="flash flash-error"
							style={{ marginBottom: "var(--md)" }}
						>
							{promptError}
						</div>
					)}
					<div className="form-grid">
						<FormField
							label="Prompt name"
							help="Internal name (e.g. 'analyze_table')."
						>
							<input
								className="form-control"
								value={promptForm.prompt_name}
								required
								onChange={(e) =>
									setPromptForm((f) => ({ ...f, prompt_name: e.target.value }))
								}
							/>
						</FormField>
						<FormField label="Display name">
							<input
								className="form-control"
								value={promptForm.display_name}
								required
								onChange={(e) =>
									setPromptForm((f) => ({ ...f, display_name: e.target.value }))
								}
							/>
						</FormField>
					</div>
					<FormField
						label="Content"
						help="Prepended to the user's message as context for the agent."
					>
						<textarea
							className="form-control"
							rows={8}
							value={promptForm.content}
							onChange={(e) =>
								setPromptForm((f) => ({ ...f, content: e.target.value }))
							}
						/>
					</FormField>
					<FormCheckbox
						label="Enabled"
						checked={promptForm.is_enabled}
						onChange={(v) => setPromptForm((f) => ({ ...f, is_enabled: v }))}
					/>
					<div className="form-actions">
						<button
							type="submit"
							className="btn btn-primary"
							disabled={savePrompt.isPending}
						>
							{savePrompt.isPending ? "Saving…" : "Save Prompt"}
						</button>
						<button
							type="button"
							className="btn btn-secondary"
							onClick={() => {
								setEditing(null);
								setPromptForm(EMPTY_PROMPT);
							}}
						>
							Cancel
						</button>
					</div>
				</form>
			)}

			<div className="card">
				{prompts.isLoading ? (
					<p className="text-sec">Loading…</p>
				) : (prompts.data?.results ?? []).length === 0 ? (
					<p className="text-sec">No prompts yet.</p>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Name</th>
									<th>Enabled</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{(prompts.data?.results ?? []).map((p) => (
									<tr key={p.id}>
										<td>
											<strong>{p.display_name}</strong>
											<div className="text-mono text-sm text-sec">
												{p.prompt_name}
											</div>
										</td>
										<td>
											<button
												type="button"
												className={
													p.is_enabled
														? "badge badge-success"
														: "badge badge-muted"
												}
												onClick={() => toggle.mutate(p.id)}
												title="Toggle enabled"
												style={{ cursor: "pointer", border: "none" }}
											>
												{p.is_enabled ? "ENABLED" : "DISABLED"}
											</button>
										</td>
										<td>
											<div className="flex-gap">
												<button
													type="button"
													className="btn btn-ghost btn-sm"
													onClick={() => openEdit(p)}
												>
													<i className="fa-solid fa-pen" /> Edit
												</button>
												<button
													type="button"
													className="btn btn-ghost btn-sm"
													style={{ color: "var(--danger)" }}
													onClick={() => {
														if (
															window.confirm(
																`Delete prompt "${p.display_name}"?`,
															)
														) {
															removePrompt.mutate(p.id);
														}
													}}
												>
													<i className="fa-solid fa-trash" /> Delete
												</button>
											</div>
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				)}
			</div>
		</div>
	);
}
