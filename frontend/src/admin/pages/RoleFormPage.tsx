import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
	createRole,
	getRole,
	getRoleGrants,
	type RoleInput,
	updateRole,
} from "../../api/admin";
import { apiErrorDetail } from "../../api/client";
import { CheckboxGroup, FormCheckbox, FormField } from "../components/forms";

const EMPTY: RoleInput = {
	name: "",
	description: "",
	is_active: true,
	can_chat: true,
	can_view_tethers: true,
	can_manage_users: false,
	is_admin_role: false,
	max_row_limit: 100,
	allowed_tools: [],
	allowed_databases: [],
	allowed_doc_sources: [],
	allowed_codebases: [],
	allowed_prompts: [],
	allowed_mcp_servers: [],
};

export function RoleFormPage() {
	const { id } = useParams();
	const isEdit = Boolean(id);
	const navigate = useNavigate();
	const queryClient = useQueryClient();
	const [form, setForm] = useState<RoleInput>(EMPTY);
	const [error, setError] = useState<string | null>(null);

	const grants = useQuery({
		queryKey: ["admin", "role-grants"],
		queryFn: getRoleGrants,
	});
	const existing = useQuery({
		queryKey: ["admin", "roles", id],
		queryFn: () => getRole(id as string),
		enabled: isEdit,
	});

	useEffect(() => {
		const r = existing.data;
		if (!r) return;
		setForm({
			name: r.name,
			description: r.description,
			is_active: r.is_active,
			can_chat: r.can_chat,
			can_view_tethers: r.can_view_tethers,
			can_manage_users: r.can_manage_users,
			is_admin_role: r.is_admin_role,
			max_row_limit: r.max_row_limit,
			allowed_tools: r.allowed_tools,
			allowed_databases: r.allowed_databases,
			allowed_doc_sources: r.allowed_doc_sources,
			allowed_codebases: r.allowed_codebases,
			allowed_prompts: r.allowed_prompts,
			allowed_mcp_servers: r.allowed_mcp_servers,
		});
	}, [existing.data]);

	function set<K extends keyof RoleInput>(key: K, value: RoleInput[K]) {
		setForm((f) => ({ ...f, [key]: value }));
	}

	const save = useMutation({
		mutationFn: (payload: RoleInput) =>
			isEdit ? updateRole(id as string, payload) : createRole(payload),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["admin", "roles"] });
			navigate("/admin/roles");
		},
		onError: (err) => setError(apiErrorDetail(err, "Save failed.")),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		save.mutate(form);
	}

	if (isEdit && existing.isLoading) {
		return (
			<div className="card">
				<p className="text-sec">Loading…</p>
			</div>
		);
	}

	const g = grants.data;

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>{isEdit ? `Edit ${form.name}` : "Add Role"}</h1>
					<p>Configure access for this role.</p>
				</div>
				<div className="form-actions">
					<Link to="/admin/roles" className="btn btn-ghost">
						Cancel
					</Link>
					<button
						type="submit"
						form="role-form"
						className="btn btn-primary"
						disabled={save.isPending}
					>
						{save.isPending
							? "Saving…"
							: isEdit
								? "Save Changes"
								: "Create Role"}
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

			<form id="role-form" onSubmit={onSubmit}>
				<div className="form-split">
					<div className="card">
						<h3 style={{ margin: "0 0 var(--md)" }}>Identity & Permissions</h3>
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
							label="Max Row Limit"
							help="Max rows per query for this role."
						>
							<input
								className="form-control"
								type="number"
								value={form.max_row_limit ?? ""}
								onChange={(e) =>
									set(
										"max_row_limit",
										e.target.value === "" ? null : Number(e.target.value),
									)
								}
							/>
						</FormField>
						<FormCheckbox
							label="Can chat"
							checked={form.can_chat}
							onChange={(v) => set("can_chat", v)}
						/>
						<FormCheckbox
							label="Can view tethers"
							checked={form.can_view_tethers}
							onChange={(v) => set("can_view_tethers", v)}
						/>
						<FormCheckbox
							label="Can manage users"
							checked={form.can_manage_users}
							onChange={(v) => set("can_manage_users", v)}
						/>
						<FormCheckbox
							label="Admin role (bypasses all restrictions)"
							checked={form.is_admin_role}
							onChange={(v) => set("is_admin_role", v)}
						/>
						<FormCheckbox
							label="Is active"
							checked={form.is_active}
							onChange={(v) => set("is_active", v)}
						/>
					</div>

					<div className="card">
						<h3 style={{ margin: "0 0 var(--md)" }}>Access Grants</h3>
						<p className="text-sec" style={{ marginTop: 0 }}>
							Ignored for admin roles, which bypass all restrictions.
						</p>
						<CheckboxGroup
							label="Databases"
							options={g?.databases ?? []}
							selected={form.allowed_databases}
							onChange={(ids) => set("allowed_databases", ids)}
						/>
						<CheckboxGroup
							label="Tools"
							options={g?.tools ?? []}
							selected={form.allowed_tools}
							onChange={(ids) => set("allowed_tools", ids)}
						/>
						<CheckboxGroup
							label="Prompts"
							options={g?.prompts ?? []}
							selected={form.allowed_prompts}
							onChange={(ids) => set("allowed_prompts", ids)}
						/>
						<CheckboxGroup
							label="Documentation Sources"
							options={g?.doc_sources ?? []}
							selected={form.allowed_doc_sources}
							onChange={(ids) => set("allowed_doc_sources", ids)}
						/>
						<CheckboxGroup
							label="Codebases"
							options={g?.codebases ?? []}
							selected={form.allowed_codebases}
							onChange={(ids) => set("allowed_codebases", ids)}
						/>
						<CheckboxGroup
							label="MCP Servers"
							options={g?.mcp_servers ?? []}
							selected={form.allowed_mcp_servers}
							onChange={(ids) => set("allowed_mcp_servers", ids)}
							help="The built-in server is always available."
						/>
					</div>
				</div>
			</form>
		</div>
	);
}
