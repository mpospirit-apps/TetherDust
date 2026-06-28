import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	type CodebaseInput,
	createCodebase,
	getCodebase,
	updateCodebase,
} from "../../api/tethers";
import { FormCheckbox, FormField } from "../components/forms";

interface FormState {
	name: string;
	description: string;
	repo_url: string;
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
	repo_url: "",
	branch: "",
	subpath: "",
	include_globs: "",
	exclude_globs: "",
	access_token: "",
	is_active: true,
};

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

	const existing = useQuery({
		queryKey: ["admin", "codebases", id],
		queryFn: () => getCodebase(id as string),
		enabled: isEdit,
	});

	useEffect(() => {
		const c = existing.data;
		if (!c) return;
		setForm({
			name: c.name,
			description: c.description,
			repo_url: c.repo_url,
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
			provider: "github",
			repo_url: form.repo_url,
			branch: form.branch,
			subpath: form.subpath,
			include_globs: linesToList(form.include_globs),
			exclude_globs: linesToList(form.exclude_globs),
			is_active: form.is_active,
		};
		if (form.access_token) payload.access_token = form.access_token;
		save.mutate(payload);
	}

	if (isEdit && existing.isLoading) {
		return (
			<div className="card">
				<p className="text-sec">Loading…</p>
			</div>
		);
	}

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>{isEdit ? `Edit ${form.name}` : "Add Codebase"}</h1>
					<p>A GitHub repository the agent can browse and read</p>
				</div>
				<Link to="/admin/codebases" className="btn btn-ghost">
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

			<form onSubmit={onSubmit} className="card" style={{ maxWidth: 640 }}>
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
				<FormField
					label="Repository URL"
					help="e.g. https://github.com/owner/repo"
				>
					<input
						className="form-control"
						value={form.repo_url}
						required
						placeholder="https://github.com/owner/repo"
						onChange={(e) => set("repo_url", e.target.value)}
					/>
				</FormField>
				<FormField
					label="Branch"
					help="Leave blank to use the repository's default branch."
				>
					<input
						className="form-control"
						value={form.branch}
						onChange={(e) => set("branch", e.target.value)}
					/>
				</FormField>
				<FormField
					label="Subpath"
					help="Optional sub-directory to scope to (e.g. services/api)."
				>
					<input
						className="form-control"
						value={form.subpath}
						onChange={(e) => set("subpath", e.target.value)}
					/>
				</FormField>
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
				<FormField
					label="Access token"
					help={
						hasToken
							? "A token is stored. Leave blank to keep it."
							: "Encrypted at rest. Leave blank for public repositories. A read-only (contents: read) fine-grained PAT is sufficient."
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
								: "Enter GitHub token"
						}
						onChange={(e) => set("access_token", e.target.value)}
					/>
				</FormField>
				<FormCheckbox
					label="Is active"
					checked={form.is_active}
					onChange={(v) => set("is_active", v)}
				/>

				<div className="form-actions">
					<button
						type="submit"
						className="btn btn-primary"
						disabled={save.isPending}
					>
						{save.isPending
							? "Saving…"
							: isEdit
								? "Save Changes"
								: "Add Codebase"}
					</button>
					<Link to="/admin/codebases" className="btn btn-ghost">
						Cancel
					</Link>
				</div>
			</form>
		</div>
	);
}
