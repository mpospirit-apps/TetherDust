import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { listRoles } from "../../api/admin";
import { apiErrorDetail } from "../../api/client";
import {
	type AdminTetherInput,
	createTether,
	getAdminTether,
	getTetherSources,
	updateTether,
} from "../../api/tethers";
import { CheckboxGroup, FormCheckbox, FormField } from "../components/forms";

interface FormState {
	name: string;
	description: string;
	code_source: string; // "codebase:<id>" | "codebasedoc:<id>"
	database_doc_source: string;
	is_active: boolean;
	allowed_roles: string[];
}

const EMPTY: FormState = {
	name: "",
	description: "",
	code_source: "",
	database_doc_source: "",
	is_active: true,
	allowed_roles: [],
};

export function TetherFormPage() {
	const { id } = useParams();
	const isEdit = Boolean(id);
	const navigate = useNavigate();
	const queryClient = useQueryClient();

	const [form, setForm] = useState<FormState>(EMPTY);
	const [error, setError] = useState<string | null>(null);

	const sources = useQuery({
		queryKey: ["admin", "tether-sources"],
		queryFn: getTetherSources,
	});
	const roles = useQuery({ queryKey: ["admin", "roles"], queryFn: listRoles });
	const existing = useQuery({
		queryKey: ["admin", "tethers", id],
		queryFn: () => getAdminTether(id as string),
		enabled: isEdit,
	});

	useEffect(() => {
		const t = existing.data;
		if (!t) return;
		const code = t.codebase
			? `codebase:${t.codebase}`
			: t.codebase_doc_source
				? `codebasedoc:${t.codebase_doc_source}`
				: "";
		setForm({
			name: t.name,
			description: t.description,
			code_source: code,
			database_doc_source: t.database_doc_source,
			is_active: t.is_active,
			allowed_roles: t.allowed_roles,
		});
	}, [existing.data]);

	function set<K extends keyof FormState>(key: K, value: FormState[K]) {
		setForm((f) => ({ ...f, [key]: value }));
	}

	const save = useMutation({
		mutationFn: (payload: AdminTetherInput) =>
			isEdit ? updateTether(id as string, payload) : createTether(payload),
		onSuccess: (t) => {
			void queryClient.invalidateQueries({ queryKey: ["admin", "tethers"] });
			navigate(`/admin/tethers/${t.id}`);
		},
		onError: (err) => setError(apiErrorDetail(err, "Save failed.")),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		const [kind, refId] = form.code_source.split(":");
		if (!kind || !refId) {
			setError("Select a codebase or codebase documentation source.");
			return;
		}
		save.mutate({
			name: form.name,
			description: form.description,
			codebase: kind === "codebase" ? refId : null,
			codebase_doc_source: kind === "codebasedoc" ? refId : null,
			database_doc_source: form.database_doc_source,
			is_active: form.is_active,
			allowed_roles: form.allowed_roles,
		});
	}

	const src = sources.data;
	const roleOptions = (roles.data?.results ?? []).map((r) => ({
		id: r.id,
		name: r.name,
	}));

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
					<h1>{isEdit ? `Edit ${form.name}` : "New Tether"}</h1>
					<p>
						{isEdit
							? "Update the tether; regenerate from its detail page."
							: "Creating a tether starts an agent generation run."}
					</p>
				</div>
				<Link to="/admin/tethers" className="btn btn-ghost">
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
				<FormField label="Description">
					<textarea
						className="form-control"
						rows={3}
						value={form.description}
						onChange={(e) => set("description", e.target.value)}
					/>
				</FormField>
				<FormField
					label="Codebase or Codebase Documentation"
					help="The code side — a live codebase repository or a codebase documentation source."
				>
					<select
						className="form-control"
						value={form.code_source}
						required
						onChange={(e) => set("code_source", e.target.value)}
					>
						<option value="">— Select a code source —</option>
						{src && src.codebases.length > 0 && (
							<optgroup label="Codebases">
								{src.codebases.map((c) => (
									<option key={c.id} value={`codebase:${c.id}`}>
										{c.name}
									</option>
								))}
							</optgroup>
						)}
						{src && src.codebase_docs.length > 0 && (
							<optgroup label="Codebase Documentation">
								{src.codebase_docs.map((d) => (
									<option key={d.id} value={`codebasedoc:${d.id}`}>
										{d.name}
									</option>
								))}
							</optgroup>
						)}
					</select>
				</FormField>
				<FormField
					label="Database documentation"
					help="The database side of this tether."
				>
					<select
						className="form-control"
						value={form.database_doc_source}
						required
						onChange={(e) => set("database_doc_source", e.target.value)}
					>
						<option value="">— Select a database source —</option>
						{(src?.database_docs ?? []).map((d) => (
							<option key={d.id} value={d.id}>
								{d.name}
							</option>
						))}
					</select>
				</FormField>
				<CheckboxGroup
					label="Allowed roles"
					help="Roles that can view this tether (staff always can)."
					options={roleOptions}
					selected={form.allowed_roles}
					onChange={(ids) => set("allowed_roles", ids)}
				/>
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
								: "Create & Generate"}
					</button>
					<Link to="/admin/tethers" className="btn btn-ghost">
						Cancel
					</Link>
				</div>
			</form>
		</div>
	);
}
