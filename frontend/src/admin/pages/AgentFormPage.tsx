import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
	type FormEvent,
	useCallback,
	useEffect,
	useRef,
	useState,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
	type AgentAuthInfo,
	type AgentInput,
	createAgent,
	getAgent,
	getAgentTypes,
	getDefaultPrompt,
	getDeviceLoginStatus,
	startDeviceLogin,
	updateAgent,
} from "../../api/admin";
import { apiErrorDetail } from "../../api/client";
import { FormField } from "../components/forms";

interface AgentForm {
	name: string;
	system_prompt: string;
	service_url: string;
	model: string;
	base_url: string;
	reasoning_effort: string;
	api_key: string;
	oauth_token: string;
}
const EMPTY: AgentForm = {
	name: "",
	system_prompt: "",
	service_url: "",
	model: "",
	base_url: "",
	reasoning_effort: "",
	api_key: "",
	oauth_token: "",
};

export function AgentFormPage() {
	const { id } = useParams();
	const isEdit = Boolean(id);
	const navigate = useNavigate();
	const queryClient = useQueryClient();

	const meta = useQuery({
		queryKey: ["admin", "agent-types"],
		queryFn: getAgentTypes,
	});
	const existing = useQuery({
		queryKey: ["admin", "agents", id],
		queryFn: () => getAgent(id as string),
		enabled: isEdit,
	});

	const [type, setType] = useState("");
	const [form, setForm] = useState<AgentForm>(EMPTY);
	const [hasKey, setHasKey] = useState(false);
	const [hasToken, setHasToken] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const seededType = useRef<string | null>(null);

	useEffect(() => {
		const a = existing.data;
		if (!a) return;
		setType(a.agent_type);
		setForm({
			name: a.name,
			system_prompt: a.system_prompt,
			service_url: a.service_url,
			model: a.model,
			base_url: a.base_url,
			reasoning_effort: a.reasoning_effort,
			api_key: "",
			oauth_token: "",
		});
		setHasKey(a.has_api_key);
		setHasToken(a.has_auth_token);
	}, [existing.data]);

	// Auto-seed the System Prompt textarea from the container default
	// (AGENTS.md/CLAUDE.md) when the agent's prompt is blank, so the admin sees
	// and can edit the prompt the agent effectively uses. Display only — saved
	// only if the form is submitted; never clobbers a non-empty prompt, and seeds
	// at most once per type.
	const promptType = isEdit ? existing.data?.agent_type : type;
	const defaultPrompt = useQuery({
		queryKey: ["admin", "agent-default-prompt", promptType],
		queryFn: () => getDefaultPrompt(promptType as string),
		enabled: Boolean(promptType),
		staleTime: Infinity,
	});
	useEffect(() => {
		const text = defaultPrompt.data?.system_prompt;
		if (!promptType || !text || seededType.current === promptType) return;
		setForm((f) => {
			if (f.system_prompt.trim() !== "") return f;
			seededType.current = promptType;
			return { ...f, system_prompt: text };
		});
	}, [defaultPrompt.data, promptType]);

	function set<K extends keyof AgentForm>(key: K, value: AgentForm[K]) {
		setForm((f) => ({ ...f, [key]: value }));
	}

	const m = meta.data;
	const isApiKey = !!m && m.api_key_types.includes(type);
	const isDirect = !!m && m.direct_api_types.includes(type);
	const isClaudeCode = type === "claude_code";
	const isCodex = type === "codex" || type === "codex_api";
	// Only the subscription Codex agent (not the API-key codex_api) uses the
	// browser device-code sign-in.
	const isCodexAuth = type === "codex";

	const save = useMutation({
		mutationFn: () => {
			const payload: AgentInput = {
				name: form.name,
				system_prompt: form.system_prompt,
				service_url: form.service_url,
				model: form.model,
			};
			if (!isEdit) payload.agent_type = type;
			if (isDirect) payload.base_url = form.base_url;
			if (isCodex) payload.reasoning_effort = form.reasoning_effort;
			if (isApiKey && form.api_key) payload.api_key = form.api_key;
			if (isClaudeCode && form.oauth_token)
				payload.oauth_token = form.oauth_token;
			return isEdit ? updateAgent(id as string, payload) : createAgent(payload);
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
			navigate("/admin/agents");
		},
		onError: (err) => setError(apiErrorDetail(err, "Save failed.")),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		save.mutate();
	}

	// Create flow, step 1: pick an integration type.
	if (!isEdit && !type) {
		return (
			<div>
				<div className="page-header">
					<div>
						<h1>Add Agent</h1>
						<p>Choose an integration type.</p>
					</div>
					<Link to="/admin/agents" className="btn btn-ghost">
						Back
					</Link>
				</div>
				{meta.isLoading ? (
					<p className="text-sec">Loading…</p>
				) : (
					(m?.categories ?? []).map((cat) => (
						<div
							className="card"
							key={cat.title}
							style={{ marginBottom: "var(--md)" }}
						>
							<h3 style={{ margin: "0 0 var(--sm)" }}>{cat.title}</h3>
							<div className="flex-gap" style={{ flexWrap: "wrap" }}>
								{cat.types.map((t) => (
									<button
										key={t.value}
										type="button"
										className="btn btn-secondary"
										onClick={() => setType(t.value)}
									>
										{t.label}
									</button>
								))}
							</div>
						</div>
					))
				)}
			</div>
		);
	}

	if (isEdit && existing.isLoading) {
		return (
			<div className="card">
				<p className="text-sec">Loading…</p>
			</div>
		);
	}

	const typeLabel = isEdit
		? (existing.data?.agent_type_display ?? "")
		: (m?.categories.flatMap((c) => c.types).find((t) => t.value === type)
				?.label ?? type);

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>{isEdit ? `Edit ${form.name}` : "Add Agent"}</h1>
					<p>{typeLabel}</p>
				</div>
				<Link to="/admin/agents" className="btn btn-ghost">
					Back
				</Link>
			</div>

			{error && (
				<div
					className="flash flash-error"
					style={{ marginBottom: "var(--md)" }}
				>
					{error}
				</div>
			)}

			{isCodexAuth && (
				<div className="card" style={{ marginBottom: "var(--md)" }}>
					<h3 style={{ margin: "0 0 var(--md)" }}>Authentication</h3>
					<p
						className="text-sec"
						style={{ margin: "0 0 var(--md)", lineHeight: 1.6 }}
					>
						TetherDust authenticates with a ChatGPT subscription
						(Plus/Pro/Enterprise). Sign in once below — the credential is stored
						encrypted and refreshed automatically.
					</p>
					{isEdit && id ? (
						<CodexDeviceLogin
							agentId={id}
							authInfo={existing.data?.auth_info ?? null}
						/>
					) : (
						<p className="text-sec" style={{ margin: 0, lineHeight: 1.6 }}>
							Save this agent first, then return to the edit screen and use{" "}
							<strong>Sign in to ChatGPT</strong> to complete device-code login
							from the browser.
						</p>
					)}
				</div>
			)}

			<form onSubmit={onSubmit}>
				<div className="card">
					<FormField label="Name">
						<input
							className="form-control"
							value={form.name}
							required
							onChange={(e) => set("name", e.target.value)}
						/>
					</FormField>
					{!isDirect && (
						<FormField
							label="Service URL"
							help="Override the agent gateway URL. Blank = default."
						>
							<input
								className="form-control"
								value={form.service_url}
								placeholder="http://codex:8002"
								onChange={(e) => set("service_url", e.target.value)}
							/>
						</FormField>
					)}
					{isApiKey && (
						<FormField
							label="API Key"
							help={hasKey ? "Leave blank to keep existing." : "Required."}
						>
							<input
								className="form-control"
								type="password"
								autoComplete="new-password"
								placeholder={
									hasKey ? "••••••••  (leave blank to keep)" : "sk-…"
								}
								value={form.api_key}
								onChange={(e) => set("api_key", e.target.value)}
							/>
						</FormField>
					)}
					{isClaudeCode && (
						<FormField
							label="OAuth Token"
							help={
								hasToken
									? "Leave blank to keep existing."
									: "From `claude setup-token`."
							}
						>
							<input
								className="form-control"
								type="password"
								autoComplete="new-password"
								placeholder={
									hasToken ? "••••••••  (leave blank to keep)" : "sk-ant-oat…"
								}
								value={form.oauth_token}
								onChange={(e) => set("oauth_token", e.target.value)}
							/>
						</FormField>
					)}
					{isDirect && (
						<FormField label="Base URL" help="OpenAI-compatible API base URL.">
							<input
								className="form-control"
								value={form.base_url}
								placeholder="https://api.openai.com/v1"
								onChange={(e) => set("base_url", e.target.value)}
							/>
						</FormField>
					)}
					<FormField label="Model" help="Leave blank for the default.">
						<input
							className="form-control"
							value={form.model}
							onChange={(e) => set("model", e.target.value)}
						/>
					</FormField>
					{isCodex && (
						<FormField label="Reasoning Effort">
							<select
								className="form-control"
								value={form.reasoning_effort}
								onChange={(e) => set("reasoning_effort", e.target.value)}
							>
								{(m?.reasoning_effort_choices ?? []).map((c) => (
									<option key={c.value} value={c.value}>
										{c.label}
									</option>
								))}
							</select>
						</FormField>
					)}
					<FormField
						label="System Prompt"
						help="Sent to the agent (AGENTS.md). Pre-filled from the container default; edit to customise, or clear to fall back to the container default."
					>
						<textarea
							className="form-control"
							rows={10}
							value={form.system_prompt}
							onChange={(e) => set("system_prompt", e.target.value)}
						/>
					</FormField>
				</div>

				<div className="form-actions" style={{ marginTop: "var(--md)" }}>
					<button
						type="submit"
						className="btn btn-primary"
						disabled={save.isPending}
					>
						{save.isPending
							? "Saving…"
							: isEdit
								? "Save Changes"
								: "Create Agent"}
					</button>
					<Link to="/admin/agents" className="btn btn-secondary">
						Cancel
					</Link>
				</div>
			</form>
		</div>
	);
}

type LoginPhase = "idle" | "starting" | "waiting" | "complete" | "error";

// Codex device-code sign-in: start the flow, show the verification URL + code,
// then poll until the user approves in a browser. On completion the backend has
// persisted the credential, so we refetch the agent to refresh the panel below.
function CodexDeviceLogin({
	agentId,
	authInfo,
}: {
	agentId: string;
	authInfo: AgentAuthInfo | null;
}) {
	const queryClient = useQueryClient();
	const [phase, setPhase] = useState<LoginPhase>("idle");
	const [prompt, setPrompt] = useState<{ url: string; code: string } | null>(
		null,
	);
	const [message, setMessage] = useState<string | null>(null);
	const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

	const stopPolling = useCallback(() => {
		if (pollRef.current !== null) {
			clearInterval(pollRef.current);
			pollRef.current = null;
		}
	}, []);

	useEffect(() => stopPolling, [stopPolling]);

	function poll(loginId: string) {
		stopPolling();
		pollRef.current = setInterval(async () => {
			try {
				const d = await getDeviceLoginStatus(agentId, loginId);
				if (d.status === "complete") {
					stopPolling();
					setPhase("complete");
					setPrompt(null);
					setMessage(null);
					queryClient.invalidateQueries({
						queryKey: ["admin", "agents", agentId],
					});
				} else if (d.status === "error" || d.status === "not_found") {
					stopPolling();
					setPhase("error");
					setMessage(d.error || `Sign-in ${d.status}.`);
				}
			} catch {
				// Transient poll error — keep waiting; the next tick may succeed.
			}
		}, 3000);
	}

	async function start() {
		stopPolling();
		setPhase("starting");
		setMessage(null);
		setPrompt(null);
		try {
			const d = await startDeviceLogin(agentId);
			setPrompt({ url: d.verification_url, code: d.user_code });
			setPhase("waiting");
			poll(d.login_id);
		} catch (err) {
			setPhase("error");
			setMessage(apiErrorDetail(err, "Failed to start sign-in."));
		}
	}

	const busy = phase === "starting" || phase === "waiting";
	const buttonLabel =
		phase === "starting"
			? "Starting…"
			: authInfo
				? "Re-authenticate"
				: "Sign in to ChatGPT";

	return (
		<div>
			{authInfo && (
				<div
					style={{
						display: "flex",
						alignItems: "center",
						gap: "var(--sm)",
						padding: "var(--sm) var(--md)",
						border: "1px solid var(--border)",
						borderRadius: 8,
						marginBottom: "var(--md)",
					}}
				>
					<span
						style={{
							width: 8,
							height: 8,
							borderRadius: "50%",
							background: "#1e7e34",
							flex: "none",
						}}
						title="Signed in"
					/>
					<div style={{ fontSize: "var(--text-sm)", lineHeight: 1.5 }}>
						<div>
							Signed in
							{authInfo.email && (
								<>
									{" "}
									as <strong>{authInfo.email}</strong>
								</>
							)}
							{authInfo.plan && (
								<span
									style={{
										display: "inline-block",
										marginLeft: "var(--xs)",
										padding: "1px 8px",
										borderRadius: 999,
										border: "1px solid var(--border)",
										color: "var(--text-sec)",
										fontSize: "var(--text-xs)",
										textTransform: "capitalize",
									}}
								>
									{authInfo.plan}
								</span>
							)}
						</div>
						{authInfo.expires_at && (
							<div className="text-sec">
								Credential renews automatically · current token expires{" "}
								{new Date(authInfo.expires_at).toLocaleString()}
							</div>
						)}
					</div>
				</div>
			)}

			<button
				type="button"
				className="btn btn-secondary"
				disabled={busy}
				onClick={start}
			>
				{buttonLabel}
			</button>
			{authInfo && (
				<div className="helptext" style={{ marginTop: "var(--xs)" }}>
					Sign in again to replace the stored credential (e.g. after expiry or
					to switch accounts).
				</div>
			)}

			<div
				style={{
					marginTop: "var(--sm)",
					fontSize: "var(--text-sm)",
					lineHeight: 1.6,
				}}
			>
				{phase === "waiting" && prompt && (
					<span>
						Go to{" "}
						<a href={prompt.url} target="_blank" rel="noopener noreferrer">
							<strong>{prompt.url}</strong>
						</a>{" "}
						and enter code <strong>{prompt.code}</strong>.<br />
						Waiting for approval…
					</span>
				)}
				{phase === "complete" && (
					<span style={{ color: "#1e7e34" }}>Signed in successfully.</span>
				)}
				{phase === "error" && message && (
					<span style={{ color: "#c0392b" }}>Sign-in failed: {message}</span>
				)}
			</div>
		</div>
	);
}
