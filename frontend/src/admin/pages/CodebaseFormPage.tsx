import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	type CodebaseInput,
	codebaseFolders,
	createCodebase,
	getCodebase,
	updateCodebase,
} from "../../api/tethers";
import { FormField, ToggleField } from "../components/forms";
import { PROVIDER_META, ProviderGlyph } from "../components/providerIcons";
import { WizardSectionHeading, type WizardStepDef } from "../components/wizard";

// Identity first, the required repository config next.
const STEPS: WizardStepDef[] = [
	{
		key: "identity",
		label: "Identity & Status",
		description: "Name the codebase and set whether it's active.",
	},
	{
		key: "configuration",
		label: "Configuration",
		description:
			"Point to the repository the agent should browse, with an access token if it's private.",
	},
];

// Mini "how to" steps shown under the local folder picker, styled like the
// wizard section headings above but in blue to read as a nested aside —
// matches the SQLite file picker's hint steps on Add Database Connection.
const LOCAL_FOLDER_HINT_STEPS: WizardStepDef[] = [
	{
		key: "place",
		label: "Place the folder",
		description:
			"Drop your codebase folder into sources/codebases/ at the project root.",
	},
	{
		key: "select",
		label: "Select it",
		description: "Pick it from the dropdown above.",
	},
];

interface FormState {
	name: string;
	description: string;
	provider: string;
	repo_url: string;
	local_root: string;
	access_token: string;
	is_active: boolean;
}

const EMPTY: FormState = {
	name: "",
	description: "",
	provider: "github",
	repo_url: "",
	local_root: "",
	access_token: "",
	is_active: true,
};

interface ProviderChoice {
	value: string;
	label: string;
}

const PROVIDER_CHOICES: ProviderChoice[] = [
	{ value: "github", label: "GitHub" },
	{ value: "gitlab", label: "GitLab" },
	{ value: "local", label: "Local" },
];

// Groups the step-1 provider picker into labeled sections (hosted Git repos
// vs. a folder on disk), matching the engine picker on Add Database
// Connection.
const PROVIDER_GROUPS: { title: string; values: string[] }[] = [
	{ title: "Remote", values: ["github", "gitlab"] },
	{ title: "Local", values: ["local"] },
];

function groupProviderChoices(
	choices: ProviderChoice[],
): { title: string; choices: ProviderChoice[] }[] {
	const byValue = new Map(choices.map((c) => [c.value, c]));
	const grouped = PROVIDER_GROUPS.map((g) => ({
		title: g.title,
		choices: g.values
			.map((v) => byValue.get(v))
			.filter((c): c is ProviderChoice => c != null),
	})).filter((g) => g.choices.length > 0);

	const groupedValues = new Set(PROVIDER_GROUPS.flatMap((g) => g.values));
	const other = choices.filter((c) => !groupedValues.has(c.value));
	if (other.length > 0) grouped.push({ title: "Other", choices: other });
	return grouped;
}

const PROVIDER_URL_PLACEHOLDER: Record<string, string> = {
	github: "https://github.com/owner/repo",
	gitlab: "https://gitlab.com/group/project",
};

const PROVIDER_TOKEN_HELP: Record<string, string> = {
	github:
		"Encrypted at rest. Leave blank for public repositories. A read-only (contents: read) fine-grained PAT is sufficient.",
	gitlab:
		"Encrypted at rest. Leave blank for public projects. A personal or project access token with the read_repository scope is sufficient.",
};

export function CodebaseFormPage() {
	const { id } = useParams();
	const isEdit = Boolean(id);
	const navigate = useNavigate();
	const queryClient = useQueryClient();

	const [form, setForm] = useState<FormState>(EMPTY);
	const [error, setError] = useState<string | null>(null);
	const [hasToken, setHasToken] = useState(false);
	const [howItWorksOpen, setHowItWorksOpen] = useState(false);
	// Create flow, step 1: pick a provider before showing the repository form.
	const [providerPicked, setProviderPicked] = useState(isEdit);

	const existing = useQuery({
		queryKey: ["admin", "codebases", id],
		queryFn: () => getCodebase(id as string),
		enabled: isEdit,
	});
	const folders = useQuery({
		queryKey: ["admin", "codebase-folders"],
		queryFn: codebaseFolders,
		enabled: form.provider === "local",
	});

	useEffect(() => {
		const c = existing.data;
		if (!c) return;
		setForm({
			name: c.name,
			description: c.description,
			provider: c.provider,
			repo_url: c.repo_url,
			local_root: c.local_root,
			access_token: "",
			is_active: c.is_active,
		});
		setHasToken(c.has_token);
	}, [existing.data]);

	function set<K extends keyof FormState>(key: K, value: FormState[K]) {
		setForm((f) => ({ ...f, [key]: value }));
	}

	const save = useMutation({
		mutationFn: (payload: CodebaseInput) =>
			isEdit ? updateCodebase(id as string, payload) : createCodebase(payload),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["admin", "codebases"] });
			navigate("/admin/codebases");
		},
		onError: (err) => setError(apiErrorDetail(err, "Save failed.")),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		const payload: CodebaseInput = {
			name: form.name,
			description: form.description,
			provider: form.provider,
			is_active: form.is_active,
		};
		if (form.provider === "local") {
			payload.local_root = form.local_root;
		} else {
			payload.repo_url = form.repo_url;
			if (form.access_token) payload.access_token = form.access_token;
		}
		save.mutate(payload);
	}

	if (isEdit && existing.isLoading) {
		return (
			<div className="card">
				<p className="text-sec">Loading…</p>
			</div>
		);
	}

	// Create flow, step 1: pick a provider.
	if (!isEdit && !providerPicked) {
		return (
			<div>
				<div className="page-header">
					<div>
						<h1>Add Codebase</h1>
						<p>Choose a repository provider</p>
					</div>
					<Link to="/admin/codebases" className="btn btn-ghost">
						Back
					</Link>
				</div>
				{groupProviderChoices(PROVIDER_CHOICES).map((group) => (
					<div className="choice-section" key={group.title}>
						<h3 className="choice-section__title">{group.title}</h3>
						<div className="choice-list choice-list--grid">
							{group.choices.map((c) => {
								const meta = PROVIDER_META[c.value];
								return (
									<button
										key={c.value}
										type="button"
										className="choice-card"
										onClick={() => {
											set("provider", c.value);
											setProviderPicked(true);
										}}
									>
										<ProviderGlyph meta={meta} />
										<div className="choice-card__body">
											<h4>{c.label}</h4>
											{meta.blurb && <p>{meta.blurb}</p>}
										</div>
										<i className="fa-solid fa-chevron-right choice-card__chevron" />
									</button>
								);
							})}
						</div>
					</div>
				))}
			</div>
		);
	}

	const providerLabel =
		PROVIDER_CHOICES.find((c) => c.value === form.provider)?.label ??
		form.provider;
	const providerMeta = PROVIDER_META[form.provider] ?? PROVIDER_META.github;
	const urlPlaceholder =
		PROVIDER_URL_PLACEHOLDER[form.provider] ?? PROVIDER_URL_PLACEHOLDER.github;
	const tokenHelp =
		PROVIDER_TOKEN_HELP[form.provider] ?? PROVIDER_TOKEN_HELP.github;
	const isLocal = form.provider === "local";
	const unregisteredFolders = (folders.data?.folders ?? []).filter(
		(f) => !f.registered || f.name === form.local_root,
	);

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>
						<span className="title-icon-tag">
							<ProviderGlyph meta={providerMeta} />
							{isEdit ? `Edit ${form.name}` : providerLabel}
						</span>
					</h1>
					<p>
						A repository the agent can browse and read (GitHub or GitLab, no
						clone)
					</p>
				</div>
				<div className="form-actions">
					<Link to="/admin/codebases" className="btn btn-ghost">
						Cancel
					</Link>
					<button
						type="submit"
						form="codebase-form"
						className="btn btn-primary"
						disabled={save.isPending}
					>
						{save.isPending
							? "Saving…"
							: isEdit
								? "Save Changes"
								: "Add Codebase"}
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

			<form id="codebase-form" onSubmit={onSubmit}>
				{!isEdit && (
					<div className="card doc-hiw-card">
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
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-code-branch" />
										</div>
										<div className="doc-hiw-label">Point at it</div>
										<div className="doc-hiw-desc">
											GitHub, GitLab (no clone needed), or a local folder under
											sources/codebases/
										</div>
									</div>
									<div className="doc-hiw-arrow">
										<i className="fa-solid fa-chevron-right" />
									</div>
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-rotate" />
										</div>
										<div className="doc-hiw-label">Kept in sync</div>
										<div className="doc-hiw-desc">
											The file tree (remote) or search index (local) refreshes
											every 6 hours, or on demand via Sync
										</div>
									</div>
									<div className="doc-hiw-arrow">
										<i className="fa-solid fa-chevron-right" />
									</div>
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-magnifying-glass-chart" />
										</div>
										<div className="doc-hiw-label">Agent browses it</div>
										<div className="doc-hiw-desc">
											Roles grant access so the agent can list, read, and search
											files via MCP
										</div>
									</div>
								</div>
							</div>
						</div>
					</div>
				)}

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
							<FormField
								label="Description"
								help="Helps the agent understand what this repo contains."
							>
								<textarea
									className="form-control"
									rows={3}
									value={form.description}
									onChange={(e) => set("description", e.target.value)}
								/>
							</FormField>
							<ToggleField
								label="Is active"
								description="The agent only browses this repo while it's active."
								checked={form.is_active}
								onChange={(v) => set("is_active", v)}
							/>
						</div>
					</div>

					<div className="wizard-section">
						<WizardSectionHeading step={STEPS[1]} index={1} />
						<div className="card">
							{isEdit && (
								<FormField label="Provider">
									<select
										className="form-control"
										value={form.provider}
										onChange={(e) => set("provider", e.target.value)}
									>
										{PROVIDER_CHOICES.map((c) => (
											<option key={c.value} value={c.value}>
												{c.label}
											</option>
										))}
									</select>
								</FormField>
							)}
							{isLocal ? (
								isEdit ? (
									<FormField
										label="Codebase Folder"
										help="Folder under sources/codebases/ (chosen at registration)."
									>
										<input
											className="form-control"
											value={form.local_root}
											disabled
										/>
									</FormField>
								) : (
									<FormField label="Codebase Folder">
										<select
											className="form-control"
											value={form.local_root}
											required
											onChange={(e) => set("local_root", e.target.value)}
										>
											<option value="">— Select a folder —</option>
											{unregisteredFolders.map((f) => (
												<option key={f.name} value={f.name}>
													{f.name}
												</option>
											))}
										</select>
										{unregisteredFolders.length === 0 && !folders.isLoading && (
											<div
												className="flash flash-error"
												style={{ marginTop: "var(--sm)" }}
											>
												No unregistered folders found in sources/codebases/. Add
												one on the server first.
											</div>
										)}
										<div className="hint-steps">
											{LOCAL_FOLDER_HINT_STEPS.map((step, i) => (
												<WizardSectionHeading
													key={step.key}
													step={step}
													index={i}
												/>
											))}
										</div>
									</FormField>
								)
							) : (
								<>
									<FormField
										label="Repository URL"
										help={`e.g. ${urlPlaceholder}`}
									>
										<input
											className="form-control"
											value={form.repo_url}
											required
											placeholder={urlPlaceholder}
											onChange={(e) => set("repo_url", e.target.value)}
										/>
									</FormField>
									<FormField
										label="Access token"
										help={
											hasToken
												? "A token is stored. Leave blank to keep it."
												: tokenHelp
										}
									>
										<input
											type="password"
											className="form-control"
											value={form.access_token}
											autoComplete="new-password"
											placeholder={
												hasToken
													? "••••••••  (leave blank to keep)"
													: `Enter ${providerLabel} token`
											}
											onChange={(e) => set("access_token", e.target.value)}
										/>
									</FormField>
								</>
							)}
						</div>
					</div>
				</div>
			</form>
		</div>
	);
}
