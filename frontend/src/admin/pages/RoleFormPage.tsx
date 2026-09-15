import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, Fragment, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
	createRole,
	type GrantOption,
	getRole,
	getRoleGrants,
	type RoleGrants,
	type RoleInput,
	updateRole,
} from "../../api/admin";
import { apiErrorDetail } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { FormField, ToggleField } from "../components/forms";
import { WizardSectionHeading, type WizardStepDef } from "../components/wizard";

// The row limit is held as the input's raw text so the field can be cleared
// while typing; `required` + `min` stop an empty or sub-1 value being submitted.
type RoleForm = Omit<RoleInput, "max_row_limit"> & { max_row_limit: string };

const EMPTY: RoleForm = {
	name: "",
	description: "",
	is_active: true,
	can_chat: true,
	can_manage_users: false,
	is_admin_role: false,
	max_row_limit: "100",
	allowed_tools: [],
	allowed_databases: [],
	allowed_doc_sources: [],
	allowed_codebases: [],
	allowed_prompts: [],
	allowed_mcp_servers: [],
	allowed_reports: [],
	allowed_dashboards: [],
	allowed_tethers: [],
};

// Identity first, what the role's users may do next, then the two allow-lists
// the agent is filtered by — what data they reach, and what it may call.
const STEPS: WizardStepDef[] = [
	{
		key: "identity",
		label: "Identity & Status",
		description: "Name the role and set whether it's active.",
	},
	{
		key: "permissions",
		label: "Permissions",
		description: "What users holding this role can do.",
	},
	{
		key: "data",
		label: "Data Access",
		description:
			"The databases, documentation and codebases its users can reach, and the reports, dashboards and tethers shared with them.",
	},
	{
		key: "tooling",
		label: "Agent Tooling",
		description:
			"The MCP tools, prompts and custom servers the agent may use for them.",
	},
];

const HOW_IT_WORKS: { icon: string; label: string; desc: string }[] = [
	{
		icon: "fa-id-badge",
		label: "Define it",
		desc: "Name the role — an inactive role grants nothing, as if its users had no role",
	},
	{
		icon: "fa-sliders",
		label: "Set permissions",
		desc: "Allow chat and cap rows per query, or make it an admin role",
	},
	{
		icon: "fa-shield-halved",
		label: "Grant access",
		desc: "Tick the data, reports, dashboards, tethers and tools it may use — nothing is granted by default",
	},
	{
		icon: "fa-users",
		label: "Assign users",
		desc: "Pick the role on each user — everything set on this page applies to them",
	},
];

type GrantKey = keyof RoleGrants;
type AllowedKey = {
	[K in keyof RoleForm]: RoleForm[K] extends string[] ? K : never;
}[keyof RoleForm];

interface GrantDef {
	key: GrantKey;
	field: AllowedKey;
	label: string;
	icon: string;
	hint: string;
	// Where to create one when the list is empty.
	addTo?: string;
	// Tools are shown by their internal name, grouped by category.
	isTools?: boolean;
}

const DATA_GRANTS: GrantDef[] = [
	{
		key: "databases",
		field: "allowed_databases",
		label: "Databases",
		icon: "fa-database",
		hint: "Queried read-only by the agent.",
		addTo: "/admin/databases/new",
	},
	{
		key: "doc_sources",
		field: "allowed_doc_sources",
		label: "Documentations",
		icon: "fa-book",
		hint: "Searched by the agent and readable under Docs.",
		addTo: "/admin/docsources/add",
	},
	{
		key: "codebases",
		field: "allowed_codebases",
		label: "Codebases",
		icon: "fa-code-branch",
		hint: "Browsed and searched by the agent.",
		addTo: "/admin/codebases/new",
	},
	{
		key: "reports",
		field: "allowed_reports",
		label: "Reports",
		icon: "fa-table-list",
		hint: "Results viewable under Reports by its users.",
		addTo: "/admin/reports/new",
	},
	{
		key: "dashboards",
		field: "allowed_dashboards",
		label: "Dashboards",
		icon: "fa-chart-bar",
		hint: "Opened under Dashboards by its users.",
		addTo: "/admin/dashboards/add",
	},
	{
		key: "tethers",
		field: "allowed_tethers",
		label: "Tethers",
		icon: "fa-diagram-project",
		hint: "Opened under Tethers by its users.",
		addTo: "/admin/tethers/new",
	},
];

const TOOLING_GRANTS: GrantDef[] = [
	{
		key: "tools",
		field: "allowed_tools",
		label: "Tools",
		icon: "fa-wrench",
		hint: "MCP tools the agent may call, built-in and custom.",
		isTools: true,
	},
	{
		key: "prompts",
		field: "allowed_prompts",
		label: "Prompts",
		icon: "fa-terminal",
		hint: "Offered as / slash commands in Chat.",
		addTo: "/admin/mcp-servers",
	},
	{
		key: "mcp_servers",
		field: "allowed_mcp_servers",
		label: "MCP Servers",
		icon: "fa-server",
		hint: "Custom servers the agent may connect to. The built-in server is always available.",
		addTo: "/admin/mcp-servers/new",
	},
];

// Tools arrive ordered by category; keep that order but put the uncategorized
// custom-server tools ("Other") last rather than first.
function groupTools(
	options: GrantOption[],
): { title: string; options: GrantOption[] }[] {
	const groups: { title: string; options: GrantOption[] }[] = [];
	const byTitle = new Map<string, GrantOption[]>();
	for (const o of options) {
		const title = o.category_label ?? "Other";
		let bucket = byTitle.get(title);
		if (!bucket) {
			bucket = [];
			byTitle.set(title, bucket);
			groups.push({ title, options: bucket });
		}
		bucket.push(o);
	}
	return groups.sort(
		(a, b) => Number(a.title === "Other") - Number(b.title === "Other"),
	);
}

function GrantPanel({
	def,
	options,
	loading,
	selected,
	onChange,
	showAddLink,
}: {
	def: GrantDef;
	options: GrantOption[];
	loading: boolean;
	selected: string[];
	onChange: (ids: string[]) => void;
	showAddLink: boolean;
}) {
	const optionIds = new Set(options.map((o) => o.id));
	const count = selected.filter((id) => optionIds.has(id)).length;
	const headingId = `grant-${def.key}`;
	// "All"/"None" only touch the listed options, so a grant the list doesn't
	// show (e.g. an MCP server that's since been deactivated) is kept as-is.
	const selectAll = () =>
		onChange([...selected.filter((id) => !optionIds.has(id)), ...optionIds]);
	const clear = () => onChange(selected.filter((id) => !optionIds.has(id)));
	const toggle = (id: string) =>
		onChange(
			selected.includes(id)
				? selected.filter((x) => x !== id)
				: [...selected, id],
		);

	const groups = def.isTools
		? groupTools(options)
		: [{ title: "", options: options }];

	return (
		<fieldset
			className={`grant-panel${def.isTools ? " grant-panel--wide" : ""}`}
			aria-labelledby={headingId}
		>
			<div className="grant-panel__head">
				<i className={`fa-solid ${def.icon} grant-panel__icon`} />
				<h4 id={headingId} className="grant-panel__title">
					{def.label}
				</h4>
				<span className={`grant-panel__count${count > 0 ? " is-some" : ""}`}>
					{count}/{options.length}
				</span>
				{options.length > 0 && (
					<div className="grant-panel__actions">
						<button
							type="button"
							className="grant-panel__action"
							disabled={count === options.length}
							onClick={selectAll}
						>
							All
						</button>
						<button
							type="button"
							className="grant-panel__action"
							disabled={count === 0}
							onClick={clear}
						>
							None
						</button>
					</div>
				)}
			</div>
			<p className="grant-panel__hint">{def.hint}</p>

			{loading ? (
				<div className="grant-panel__empty">Loading…</div>
			) : options.length === 0 ? (
				<div className="grant-panel__empty">
					None yet.
					{showAddLink && def.addTo && (
						<>
							{" "}
							<Link to={def.addTo}>Add one</Link>
						</>
					)}
				</div>
			) : (
				<div
					className={`grant-list${def.isTools ? " grant-list--columns" : ""}`}
				>
					{groups.map((group) => (
						<div className="grant-list__group" key={group.title}>
							{group.title && (
								<div className="grant-list__group-title">{group.title}</div>
							)}
							{group.options.map((o) => {
								const checked = selected.includes(o.id);
								return (
									<label
										key={o.id}
										className={`grant-item${checked ? " is-checked" : ""}`}
									>
										<input
											type="checkbox"
											checked={checked}
											onChange={() => toggle(o.id)}
										/>
										<span
											className={`grant-item__name${def.isTools ? " is-mono" : ""}`}
										>
											{o.name}
										</span>
										{!o.is_active && (
											<span
												className="grant-item__tag"
												title="Granting it has no effect until it's active again."
											>
												Inactive
											</span>
										)}
									</label>
								);
							})}
						</div>
					))}
				</div>
			)}
		</fieldset>
	);
}

export function RoleFormPage() {
	const { id } = useParams();
	const isEdit = Boolean(id);
	const navigate = useNavigate();
	const queryClient = useQueryClient();
	// Editing a role is user management: staff without it get a read-only view.
	const readOnly = !(useAuth().user?.can_manage_users ?? false);
	const [form, setForm] = useState<RoleForm>(EMPTY);
	const [error, setError] = useState<string | null>(null);
	const [howItWorksOpen, setHowItWorksOpen] = useState(false);

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
			can_manage_users: r.can_manage_users,
			is_admin_role: r.is_admin_role,
			max_row_limit: String(r.max_row_limit),
			allowed_tools: r.allowed_tools,
			allowed_databases: r.allowed_databases,
			allowed_doc_sources: r.allowed_doc_sources,
			allowed_codebases: r.allowed_codebases,
			allowed_prompts: r.allowed_prompts,
			allowed_mcp_servers: r.allowed_mcp_servers,
			allowed_reports: r.allowed_reports,
			allowed_dashboards: r.allowed_dashboards,
			allowed_tethers: r.allowed_tethers,
		});
	}, [existing.data]);

	function set<K extends keyof RoleForm>(key: K, value: RoleForm[K]) {
		setForm((f) => ({ ...f, [key]: value }));
	}

	const save = useMutation({
		mutationFn: (payload: RoleInput) =>
			isEdit ? updateRole(id as string, payload) : createRole(payload),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["admin", "roles"] });
			// Report, dashboard and tether sharing is the same relation their own
			// forms edit as "Allowed roles".
			for (const key of ["reports", "dashboards", "tethers"]) {
				queryClient.invalidateQueries({ queryKey: ["admin", key] });
			}
			navigate("/admin/roles");
		},
		onError: (err) => setError(apiErrorDetail(err, "Save failed.")),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		// An admin role disables the row-limit field, which also skips its
		// `required` check — fall back to the default rather than send 0.
		const rowLimit = form.max_row_limit || EMPTY.max_row_limit;
		save.mutate({ ...form, max_row_limit: Number(rowLimit) });
	}

	if (isEdit && existing.isLoading) {
		return (
			<div className="card">
				<p className="text-sec">Loading…</p>
			</div>
		);
	}

	const isAdmin = form.is_admin_role;

	function renderGrants(defs: GrantDef[]) {
		return defs.map((def) => (
			<GrantPanel
				key={def.key}
				def={def}
				options={grants.data?.[def.key] ?? []}
				loading={grants.isLoading}
				selected={form[def.field]}
				onChange={(ids) => set(def.field, ids)}
				showAddLink={!readOnly}
			/>
		));
	}

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>
						{!isEdit ? "Add Role" : readOnly ? form.name : `Edit ${form.name}`}
					</h1>
					<p>A set of permissions and access grants you assign to users</p>
				</div>
				<div className="form-actions">
					<Link to="/admin/roles" className="btn btn-ghost">
						{readOnly ? "Back" : "Cancel"}
					</Link>
					{!readOnly && (
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
					)}
				</div>
			</div>

			{readOnly && (
				<div className="flash flash-info" style={{ marginBottom: "var(--md)" }}>
					Read-only. Changing a role changes what every user holding it can
					reach, so it needs the "Can manage users" permission.
				</div>
			)}

			{error && (
				<div
					className="flash flash-error"
					style={{ marginBottom: "var(--md)" }}
				>
					{error}
				</div>
			)}

			<form id="role-form" className="form-dim-disabled" onSubmit={onSubmit}>
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
									{HOW_IT_WORKS.map((step, i) => (
										<Fragment key={step.label}>
											{i > 0 && (
												<div className="doc-hiw-arrow">
													<i className="fa-solid fa-chevron-right" />
												</div>
											)}
											<div className="doc-hiw-step">
												<div className="doc-hiw-icon">
													<i className={`fa-solid ${step.icon}`} />
												</div>
												<div className="doc-hiw-label">{step.label}</div>
												<div className="doc-hiw-desc">{step.desc}</div>
											</div>
										</Fragment>
									))}
								</div>
							</div>
						</div>
					</div>
				)}

				<fieldset className="form-fieldset" disabled={readOnly}>
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
										help="Who this role is for, so it's easy to pick on a user."
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
										description="An inactive role grants nothing — its users are treated as having no role."
										checked={form.is_active}
										onChange={(v) => set("is_active", v)}
									/>
								</div>
							</div>

							<div className="wizard-section">
								<WizardSectionHeading step={STEPS[1]} index={1} />
								<div className="card">
									<FormField
										label="Max Row Limit"
										help={
											isAdmin
												? "Not applied — admin roles have no row limit."
												: "The most rows any single query returns for these users."
										}
									>
										<input
											className="form-control"
											type="number"
											min={1}
											step={1}
											required
											disabled={isAdmin}
											value={form.max_row_limit}
											onChange={(e) => set("max_row_limit", e.target.value)}
										/>
									</FormField>
									<ToggleField
										label="Can chat"
										description="Users can open Chat and ask the agent questions."
										checked={isAdmin || form.can_chat}
										disabled={isAdmin}
										onChange={(v) => set("can_chat", v)}
									/>

									<div className="role-admin-block">
										<ToggleField
											label="Admin role"
											description="Makes its users staff with console access and lifts every restriction on this page."
											checked={form.is_admin_role}
											onChange={(v) => set("is_admin_role", v)}
										/>
										<ToggleField
											label="Can manage users"
											description={
												isAdmin
													? "Its staff can add, edit and delete users and roles."
													: "Needs Admin role — only staff reach user and role management."
											}
											checked={form.can_manage_users}
											disabled={!isAdmin}
											onChange={(v) => set("can_manage_users", v)}
										/>
									</div>
								</div>
							</div>
						</div>

						{isAdmin && (
							<div className="flash flash-info role-bypass-note">
								<i className="fa-solid fa-crown" /> Admin role — its users can
								reach everything, so the access grants below are ignored.
							</div>
						)}

						<fieldset
							className={`form-fieldset role-grants${isAdmin ? " is-bypassed" : ""}`}
							disabled={isAdmin}
						>
							<div className="wizard-section">
								<WizardSectionHeading step={STEPS[2]} index={2} />
								<div className="card">
									<div className="grant-grid grant-grid--data">
										{renderGrants(DATA_GRANTS)}
									</div>
								</div>
							</div>

							<div className="wizard-section">
								<WizardSectionHeading step={STEPS[3]} index={3} />
								<div className="card">
									<div className="grant-grid grant-grid--tooling">
										{renderGrants(TOOLING_GRANTS)}
									</div>
								</div>
							</div>
						</fieldset>
					</div>
				</fieldset>
			</form>
		</div>
	);
}
