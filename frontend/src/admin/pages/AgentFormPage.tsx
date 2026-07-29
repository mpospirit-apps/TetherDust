import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
	type FormEvent,
	Fragment,
	useCallback,
	useEffect,
	useRef,
	useState,
} from "react";
import Markdown from "react-markdown";
import { Link, useNavigate, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";
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
import {
	AGENT_TYPE_ICONS,
	AgentIconGlyph,
	DEFAULT_AGENT_ICON,
} from "../components/agentIcons";
import { FormField } from "../components/forms";
import { WizardSectionHeading, type WizardStepDef } from "../components/wizard";

// Create flow: identity first, the required gateway/model/credentials config
// next, the system prompt (read-only) last.
const STEPS: WizardStepDef[] = [
	{
		key: "identity",
		label: "Identity",
		description: "Name the agent.",
	},
	{
		key: "configuration",
		label: "Configuration",
		description: "Set the gateway, model, and credentials.",
	},
	{
		key: "system_prompt",
		label: "System Prompt",
		description: "Read-only — the instructions sent to the agent.",
	},
];

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
// The section title already conveys "API Key" (see AGENT_TYPE_CATEGORIES on
// the backend), so strip the redundant "(API key)" suffix from individual
// card titles in the step-1 picker.
function cardLabel(label: string): string {
	return label.replace(/\s*\(API key\)\s*$/i, "");
}

interface ModelHelp {
	placeholder: string;
	help: string;
}

// The Model field is just a free-text string passed straight through to the
// CLI/API (`codex exec -c model=`, `claude --model`, or the request body for
// Direct API types), so there's no dropdown to discover valid values from —
// hence per-type examples. CLI types (Codex, Claude Code) fall back to the
// CLI's own default when blank; Direct API types have no such fallback, so
// the model is required there.
const MODEL_HELP: Record<string, ModelHelp> = {
	codex: {
		placeholder: "gpt-5.4-codex",
		help: "e.g. gpt-5.4, gpt-5.4-codex — leave blank to use the CLI's current default. Run `codex --help` or check OpenAI's Codex docs for the exact current model IDs.",
	},
	codex_api: {
		placeholder: "gpt-5.4-codex",
		help: "e.g. gpt-5.4, gpt-5.4-codex — leave blank to use the CLI's current default. Run `codex --help` or check OpenAI's Codex docs for the exact current model IDs.",
	},
	claude_code: {
		placeholder: "claude-sonnet-5",
		help: "e.g. claude-sonnet-5, claude-opus-4-8, claude-haiku-4-5-20251001 (or aliases like sonnet/opus/haiku). Leave blank to use the CLI's default.",
	},
	claude_code_api: {
		placeholder: "claude-sonnet-5",
		help: "e.g. claude-sonnet-5, claude-opus-4-8, claude-haiku-4-5-20251001 (or aliases like sonnet/opus/haiku). Leave blank to use the CLI's default.",
	},
	openai_platform: {
		placeholder: "gpt-5.4",
		help: "e.g. gpt-5.4, gpt-5.4-mini. Required — see OpenAI's model list for the exact current IDs.",
	},
	claude_console: {
		placeholder: "claude-sonnet-5",
		help: "e.g. claude-sonnet-5, claude-opus-4-8, claude-haiku-4-5-20251001. Required.",
	},
	openai_api: {
		placeholder: "llama-3.3-70b-instruct",
		help: "The model identifier your OpenAI-compatible endpoint expects (its docs will list the exact string). Required.",
	},
	ollama: {
		placeholder: "llama3.3",
		help: "The local model tag, e.g. llama3.3, qwen2.5-coder, mistral — must already be pulled (`ollama pull <name>`). Required.",
	},
	openrouter: {
		placeholder: "anthropic/claude-sonnet-5",
		help: "OpenRouter's provider/model slug, e.g. anthropic/claude-sonnet-5, openai/gpt-5.4 — see openrouter.ai/models for the full list. Required.",
	},
};

const DEFAULT_MODEL_HELP: ModelHelp = {
	placeholder: "",
	help: "Leave blank for the default.",
};

// Mini "how to" steps shown under the Base URL field for Ollama, styled like
// the SQLite file-picker hint on Add Database Connection. Ollama runs on the
// admin's own machine, not in this app's Docker network, so `localhost` from
// inside the `backend` container doesn't reach it — hence the
// `host.docker.internal` callout.
const OLLAMA_HINT_STEPS: WizardStepDef[] = [
	{
		key: "serve",
		label: "Serve the model",
		description:
			"Run `ollama pull <model>` then `ollama serve` (or just `ollama run <model>` to do both) on the machine running Ollama.",
	},
	{
		key: "host",
		label: "Point at your machine",
		description:
			"Use http://host.docker.internal:11434/v1 as the Base URL below, not localhost — the agent runs inside a container, so localhost there means the container itself.",
	},
	{
		key: "tag",
		label: "Match the model tag",
		description: "Use the exact tag from `ollama list` as the Model above.",
	},
];

interface HiwStep {
	icon: string;
	label: string;
	desc: string;
}

// Per-method "How it works" steps. Each integration type is set up differently
// (subscription device-login vs. pasted token vs. API key vs. in-process), so
// the overview walks through that method's specific path. Every CLI-backed
// method (Codex, Claude Code) also gets its own explicit "MCP tools only" step:
// as of 0.7.0 the CLI's built-in tools (shell exec, file edits) are disabled/not
// granted, so the model can only reach the built-in + custom MCP tools your
// roles allow — see `features.shell_tool=false` in the Codex gateway and
// `--allowedTools` in the Claude Code gateway.
function howItWorksSteps(flags: {
	isCodexAuth: boolean;
	isCodexApiKey: boolean;
	isClaudeCodeAuth: boolean;
	isClaudeApiKey: boolean;
	isDirect: boolean;
}): HiwStep[] {
	const nameIt: HiwStep = {
		icon: "fa-signature",
		label: "Name it",
		desc: "Give the agent a name so you can recognise it in the list.",
	};
	const setModel: HiwStep = {
		icon: "fa-sliders",
		label: "Set the model",
		desc: "Choose the model (and reasoning effort for Codex), or leave blank for the default.",
	};
	const saveAndActivate: HiwStep = {
		icon: "fa-floppy-disk",
		label: "Save & activate",
		desc: "Create the agent, then make it the active one.",
	};
	if (flags.isDirect) {
		return [
			nameIt,
			{
				icon: "fa-link",
				label: "Point at the API",
				desc: "Set the OpenAI-compatible base URL and API key for the provider.",
			},
			setModel,
			saveAndActivate,
			{
				icon: "fa-bolt",
				label: "Runs in-process",
				desc: "TetherDust drives the tool-call loop itself — no CLI, no shell or filesystem access — calling only MCP tools.",
			},
		];
	}
	if (flags.isCodexApiKey) {
		return [
			nameIt,
			{
				icon: "fa-key",
				label: "Paste the API key",
				desc: "Provide the OpenAI API key; usage is billed per token against that key.",
			},
			setModel,
			saveAndActivate,
			{
				icon: "fa-terminal",
				label: "Chat routes to Codex",
				desc: "Questions run through `codex exec` behind the gateway.",
			},
			{
				icon: "fa-lock",
				label: "MCP tools only",
				desc: "Codex's built-in shell tool is disabled, so the model has no way to read container files or run commands — it can only call the MCP tools your roles allow.",
			},
		];
	}
	if (flags.isClaudeApiKey) {
		return [
			nameIt,
			{
				icon: "fa-key",
				label: "Paste the API key",
				desc: "Provide the Anthropic API key; usage is billed per token against that key.",
			},
			setModel,
			saveAndActivate,
			{
				icon: "fa-terminal",
				label: "Chat routes to Claude Code",
				desc: "Questions run through `claude -p` behind the gateway.",
			},
			{
				icon: "fa-lock",
				label: "MCP tools only",
				desc: "Claude Code's own built-in tools (Bash, file edits) aren't granted — `--allowedTools` scopes it to only the MCP tools your roles allow.",
			},
		];
	}
	if (flags.isClaudeCodeAuth) {
		return [
			nameIt,
			{
				icon: "fa-key",
				label: "Paste the OAuth token",
				desc: "Run `claude setup-token` locally and paste the sk-ant-oat… token here.",
			},
			setModel,
			saveAndActivate,
			{
				icon: "fa-terminal",
				label: "Chat routes to Claude Code",
				desc: "Questions run through `claude -p` behind the gateway.",
			},
			{
				icon: "fa-lock",
				label: "MCP tools only",
				desc: "Claude Code's own built-in tools (Bash, file edits) aren't granted — `--allowedTools` scopes it to only the MCP tools your roles allow.",
			},
		];
	}
	// Codex subscription (auth-token) — the only method with browser device login.
	return [
		nameIt,
		setModel,
		{
			icon: "fa-floppy-disk",
			label: "Save first",
			desc: "Create the agent — you'll land back here to finish sign-in.",
		},
		{
			icon: "fa-right-to-bracket",
			label: "Sign in to ChatGPT",
			desc: "Approve the device-code login in your browser; the credential is stored encrypted and auto-refreshed.",
		},
		{
			icon: "fa-terminal",
			label: "Chat routes to Codex",
			desc: "Once active, questions run through `codex exec` behind the gateway.",
		},
		{
			icon: "fa-lock",
			label: "MCP tools only",
			desc: "Codex's built-in shell tool is disabled, so the model has no way to read container files or run commands — it can only call the MCP tools your roles allow.",
		},
	];
}

// Deep-links straight to the repo's "Agent method request" issue template
// (.github/ISSUE_TEMPLATE/agent_support.md) instead of the generic issues
// list — mirrors GITHUB_DATABASE_REQUEST_URL on Add Database Connection.
const GITHUB_AGENT_REQUEST_URL =
	"https://github.com/mpospirit-apps/TetherDust/issues/new?template=agent_support.md";

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
	const [howItWorksOpen, setHowItWorksOpen] = useState(false);
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
	const isCodexApiKey = type === "codex_api";
	const isClaudeApiKey = type === "claude_code_api";
	const isOllama = type === "ollama";

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
		onSuccess: (agent) => {
			queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
			// Land on the new agent's edit screen instead of the list — the Codex
			// subscription type needs a saved agent before its "Sign in to
			// ChatGPT" panel can appear (see CodexDeviceLogin below), so this
			// saves a manual "find it, click Edit" round trip.
			navigate(isEdit ? "/admin/agents" : `/admin/agents/${agent.id}`);
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
						<div className="choice-section" key={cat.title}>
							<h3 className="choice-section__title">{cat.title}</h3>
							<div className="choice-list choice-list--grid">
								{cat.types.map((t) => (
									<button
										key={t.value}
										type="button"
										className="choice-card"
										onClick={() => setType(t.value)}
									>
										<AgentIconGlyph
											icon={AGENT_TYPE_ICONS[t.value] ?? DEFAULT_AGENT_ICON}
										/>
										<div className="choice-card__body">
											<h4>{cardLabel(t.label)}</h4>
										</div>
										<i className="fa-solid fa-chevron-right choice-card__chevron" />
									</button>
								))}
							</div>
						</div>
					))
				)}
				<div className="choice-section">
					<h3 className="choice-section__title">
						Not finding what you're looking for?
					</h3>
					<div className="choice-list choice-list--grid">
						<a
							href={GITHUB_AGENT_REQUEST_URL}
							target="_blank"
							rel="noopener noreferrer"
							className="choice-card"
						>
							<i className="fa-brands fa-github choice-card__icon" />
							<div className="choice-card__body">
								<h4>Request an agent method</h4>
								<p>
									Open a feature request on GitHub if your agent or gateway
									isn't listed.
								</p>
							</div>
							<i className="fa-solid fa-arrow-up-right-from-square choice-card__chevron" />
						</a>
					</div>
				</div>
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
	const modelHelp = MODEL_HELP[type] ?? DEFAULT_MODEL_HELP;

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>
						<span className="title-icon-tag">
							<AgentIconGlyph
								icon={AGENT_TYPE_ICONS[type] ?? DEFAULT_AGENT_ICON}
							/>
							{isEdit ? `Edit ${form.name}` : "Add Agent"}
						</span>
					</h1>
					<p>{typeLabel}</p>
				</div>
				<div className="form-actions">
					<Link to="/admin/agents" className="btn btn-ghost">
						Cancel
					</Link>
					<button
						type="submit"
						form="agent-form"
						className="btn btn-primary"
						disabled={save.isPending}
					>
						{save.isPending
							? "Saving…"
							: isEdit
								? "Save Changes"
								: "Create Agent"}
					</button>
				</div>
			</div>

			{error && (
				<div
					className="flash flash-error"
					style={{ marginBottom: "var(--md)" }}
				>
					{error}
				</div>
			)}

			{!isEdit && (
				<div
					className="card doc-hiw-card"
					style={{ marginBottom: "var(--md)" }}
				>
					<button
						type="button"
						className="doc-hiw-toggle"
						aria-expanded={howItWorksOpen}
						onClick={() => setHowItWorksOpen((open) => !open)}
					>
						<h3>How it works</h3>
						<i
							className={`fa-solid fa-chevron-down doc-hiw-chevron${
								howItWorksOpen ? " is-open" : ""
							}`}
						/>
					</button>
					<div
						className={`doc-hiw-collapse${howItWorksOpen ? " is-open" : ""}`}
					>
						<div className="doc-hiw-collapse__inner">
							<div className="doc-hiw">
								{howItWorksSteps({
									isCodexAuth,
									isCodexApiKey,
									isClaudeCodeAuth: isClaudeCode,
									isClaudeApiKey,
									isDirect,
								}).map((step, i, steps) => (
									<Fragment key={step.label}>
										<div className="doc-hiw-step">
											<div className="doc-hiw-icon">
												<i className={`fa-solid ${step.icon}`} />
											</div>
											<div className="doc-hiw-label">{step.label}</div>
											<div className="doc-hiw-desc">{step.desc}</div>
										</div>
										{i < steps.length - 1 && (
											<div className="doc-hiw-arrow">
												<i className="fa-solid fa-chevron-right" />
											</div>
										)}
									</Fragment>
								))}
							</div>
						</div>
					</div>
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
							Save this agent to continue — you'll land back here with a{" "}
							<strong>Sign in to ChatGPT</strong> button to complete device-code
							login from the browser.
						</p>
					)}
				</div>
			)}

			<form id="agent-form" onSubmit={onSubmit}>
				<div className="form-split-col">
					<div className="form-split">
						<div className="wizard-section">
							<WizardSectionHeading step={STEPS[0]} index={0} />
							<div className="card">
								<FormField label="Name">
									<input
										className="form-control"
										value={form.name}
										required
										onChange={(e) => set("name", e.target.value)}
									/>
								</FormField>
							</div>
						</div>

						<div className="wizard-section">
							<WizardSectionHeading step={STEPS[1]} index={1} />
							<div className="card">
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
								<FormField label="Model" help={modelHelp.help}>
									<input
										className="form-control"
										value={form.model}
										placeholder={modelHelp.placeholder}
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
								{isApiKey && (
									<FormField
										label="API Key"
										help={
											isEdit
												? hasKey
													? "Leave blank to keep existing."
													: "Required."
												: "Required."
										}
									>
										<input
											className="form-control"
											type="password"
											autoComplete="new-password"
											placeholder={
												isEdit && hasKey
													? "••••••••  (leave blank to keep)"
													: "sk-…"
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
											isEdit && hasToken
												? "Leave blank to keep existing."
												: "From `claude setup-token`."
										}
									>
										<input
											className="form-control"
											type="password"
											autoComplete="new-password"
											placeholder={
												isEdit && hasToken
													? "••••••••  (leave blank to keep)"
													: "sk-ant-oat…"
											}
											value={form.oauth_token}
											onChange={(e) => set("oauth_token", e.target.value)}
										/>
									</FormField>
								)}
								{isDirect && (
									<FormField
										label="Base URL"
										help="OpenAI-compatible API base URL."
									>
										<input
											className="form-control"
											value={form.base_url}
											placeholder={
												isOllama
													? "http://host.docker.internal:11434/v1"
													: "https://api.openai.com/v1"
											}
											onChange={(e) => set("base_url", e.target.value)}
										/>
										{isOllama && (
											<div className="hint-steps">
												{OLLAMA_HINT_STEPS.map((step, i) => (
													<WizardSectionHeading
														key={step.key}
														step={step}
														index={i}
													/>
												))}
											</div>
										)}
									</FormField>
								)}
								{!isApiKey && !isClaudeCode && !isDirect && (
									<p className="text-sec text-sm" style={{ margin: 0 }}>
										No additional credentials required
										{isCodexAuth ? " — sign in above." : "."}
									</p>
								)}
							</div>
						</div>
					</div>

					<div className="wizard-section">
						<WizardSectionHeading step={STEPS[2]} index={2} />
						<div className="card">
							<FormField
								label="System Prompt"
								help="Read-only — the instructions sent to the agent (AGENTS.md / CLAUDE.md container default)."
							>
								<div className="doc-result-preview__content">
									<Markdown remarkPlugins={[remarkGfm]}>
										{form.system_prompt ||
											(defaultPrompt.isLoading ? "_Loading…_" : "_(empty)_")}
									</Markdown>
								</div>
							</FormField>
						</div>
					</div>
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
