import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { siGithub, siGitlab } from "simple-icons";
import { apiErrorDetail } from "../../api/client";
import {
	type CodebaseInput,
	codebaseFolders,
	createCodebase,
	getCodebase,
	updateCodebase,
} from "../../api/tethers";
import { FormField, ToggleField } from "../components/forms";
import { WizardSectionHeading, type WizardStepDef } from "../components/wizard";

// Identity first, the required repository config next, optional/advanced
// fields last.
const STEPS: WizardStepDef[] = [
	{
		key: "identity",
		label: "Identity & Status",
		description: "Name the codebase and set whether it's active.",
	},
	{
		key: "configuration",
		label: "Configuration",
		description: "Point to the repository the agent should browse.",
	},
	{
		key: "optional",
		label: "Optional Configurations",
		description: "Optional — branch, path filters, and access token.",
	},
];

interface FormState {
	name: string;
	description: string;
	provider: string;
	repo_url: string;
	local_root: string;
	branch: string;
	subpath: string;
	include_globs: string;
	exclude_globs: string;
	access_token: string;
	is_active: boolean;
}

const EMPTY: FormState = {
	name: "",
	description: "",
	provider: "github",
	repo_url: "",
	local_root: "",
	branch: "",
	subpath: "",
	include_globs: "",
	exclude_globs: "",
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

interface ProviderMeta {
	icon?: { title: string; path: string };
	faIcon?: string;
	blurb: string;
}

const PROVIDER_META: Record<string, ProviderMeta> = {
	github: {
		icon: { title: siGithub.title, path: siGithub.path },
		blurb: "Public or private GitHub repository.",
	},
	gitlab: {
		icon: { title: siGitlab.title, path: siGitlab.path },
		blurb:
			"Public or private GitLab.com repository (self-managed instances aren't supported).",
	},
	local: {
		faIcon: "fa-folder-open",
		blurb:
			"A folder placed under sources/codebases/ on the server. Read live from disk and searched semantically — no clone, no token.",
	},
};

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

function ProviderIconGlyph({
	icon,
}: {
	icon: { title: string; path: string };
}) {
	return (
		<span className="choice-card__icon choice-card__icon--logo">
			<svg role="img" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
				<title>{icon.title}</title>
				<path d={icon.path} />
			</svg>
		</span>
	);
}

function ProviderGlyph({ meta }: { meta: ProviderMeta }) {
	if (meta.faIcon) {
		return (
			<span className="choice-card__icon">
				<i className={`fa-solid ${meta.faIcon}`} />
			</span>
		);
	}
	if (meta.icon) return <ProviderIconGlyph icon={meta.icon} />;
	return null;
}

function linesToList(value: string): string[] {
	return value
		.split("\n")
		.map((s) => s.trim())
		.filter(Boolean);
}

export function CodebaseFormPage() {
	const { id } = useParams();
	const isEdit = Boolean(id);
	const navigate = useNavigate();
	const queryClient = useQueryClient();

	const [form, setForm] = useState<FormState>(EMPTY);
	const [error, setError] = useState<string | null>(null);
	const [hasToken, setHasToken] = useState(false);
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
			branch: c.branch,
			subpath: c.subpath,
			include_globs: c.include_globs.join("\n"),
			exclude_globs: c.exclude_globs.join("\n"),
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
			subpath: form.subpath,
			include_globs: linesToList(form.include_globs),
			exclude_globs: linesToList(form.exclude_globs),
			is_active: form.is_active,
		};
		if (form.provider === "local") {
			payload.local_root = form.local_root;
		} else {
			payload.repo_url = form.repo_url;
			payload.branch = form.branch;
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
				<div className="choice-list choice-list--grid">
					{PROVIDER_CHOICES.map((c) => {
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
						{isEdit ? (
							`Edit ${form.name}`
						) : (
							<span className="title-icon-tag">
								<ProviderGlyph meta={providerMeta} />
								{providerLabel}
							</span>
						)}
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
				{isEdit ? (
					<div className="form-split">
						<div className="card">
							<h3 style={{ margin: "0 0 var(--md)" }}>Identity</h3>
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

						<div className="card">
							<h3 style={{ margin: "0 0 var(--md)" }}>Repository</h3>
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
							{isLocal ? (
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
							)}
							<div className="form-grid">
								{!isLocal && (
									<FormField
										label="Branch"
										help="Leave blank to use the default branch."
									>
										<input
											className="form-control"
											value={form.branch}
											onChange={(e) => set("branch", e.target.value)}
										/>
									</FormField>
								)}
								<FormField label="Subpath" help="e.g. services/api">
									<input
										className="form-control"
										value={form.subpath}
										onChange={(e) => set("subpath", e.target.value)}
									/>
								</FormField>
							</div>
							<FormField
								label="Include globs"
								help="One glob per line, e.g. src/**. Empty = everything."
							>
								<textarea
									className="form-control"
									rows={2}
									value={form.include_globs}
									onChange={(e) => set("include_globs", e.target.value)}
									placeholder={"src/**\n*.py"}
								/>
							</FormField>
							<FormField
								label="Exclude globs"
								help="One glob per line. Empty = a sensible default set (node_modules, build output, binaries)."
							>
								<textarea
									className="form-control"
									rows={2}
									value={form.exclude_globs}
									onChange={(e) => set("exclude_globs", e.target.value)}
									placeholder={"node_modules/*\n*.lock"}
								/>
							</FormField>
							{!isLocal && (
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
							)}
						</div>
					</div>
				) : (
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
									{isLocal ? (
										<FormField
											label="Codebase Folder"
											help="Select a folder from sources/codebases/."
										>
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
											{unregisteredFolders.length === 0 &&
												!folders.isLoading && (
													<div className="helptext">
														No unregistered folders found under
														sources/codebases/. Add one on the server first.
													</div>
												)}
										</FormField>
									) : (
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
									)}
								</div>
							</div>
						</div>

						<div className="wizard-section">
							<WizardSectionHeading step={STEPS[2]} index={2} />
							<div className="card">
								<div className="form-grid">
									{!isLocal && (
										<FormField
											label="Branch"
											help="Leave blank to use the default branch."
										>
											<input
												className="form-control"
												value={form.branch}
												onChange={(e) => set("branch", e.target.value)}
											/>
										</FormField>
									)}
									<FormField label="Subpath" help="e.g. services/api">
										<input
											className="form-control"
											value={form.subpath}
											onChange={(e) => set("subpath", e.target.value)}
										/>
									</FormField>
								</div>
								<FormField
									label="Include globs"
									help="One glob per line, e.g. src/**. Empty = everything."
								>
									<textarea
										className="form-control"
										rows={2}
										value={form.include_globs}
										onChange={(e) => set("include_globs", e.target.value)}
										placeholder={"src/**\n*.py"}
									/>
								</FormField>
								<FormField
									label="Exclude globs"
									help="One glob per line. Empty = a sensible default set (node_modules, build output, binaries)."
								>
									<textarea
										className="form-control"
										rows={2}
										value={form.exclude_globs}
										onChange={(e) => set("exclude_globs", e.target.value)}
										placeholder={"node_modules/*\n*.lock"}
									/>
								</FormField>
								{!isLocal && (
									<FormField label="Access token" help={tokenHelp}>
										<input
											type="password"
											className="form-control"
											value={form.access_token}
											autoComplete="new-password"
											placeholder={`Enter ${providerLabel} token`}
											onChange={(e) => set("access_token", e.target.value)}
										/>
									</FormField>
								)}
							</div>
						</div>
					</div>
				)}
			</form>
		</div>
	);
}
