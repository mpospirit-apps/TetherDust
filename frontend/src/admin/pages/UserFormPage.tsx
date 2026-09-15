import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, Fragment, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
	createUser,
	getUser,
	listRoles,
	type Role,
	type UserInput,
	updateUser,
} from "../../api/admin";
import { apiErrorDetail } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { CustomSelect, FormField, ToggleField } from "../components/forms";
import { WizardSectionHeading, type WizardStepDef } from "../components/wizard";

interface UserForm {
	username: string;
	email: string;
	password: string;
	confirm_password: string;
	is_active: boolean;
	role: string;
}

const EMPTY: UserForm = {
	username: "",
	email: "",
	password: "",
	confirm_password: "",
	is_active: true,
	role: "",
};

const STEPS: WizardStepDef[] = [
	{
		key: "account",
		label: "Account",
		description: "The sign-in details for this person.",
	},
	{
		key: "access",
		label: "Access",
		description:
			"The role they get their access from, and whether they can sign in.",
	},
];

const HOW_IT_WORKS: { icon: string; label: string; desc: string }[] = [
	{
		icon: "fa-user-plus",
		label: "Create the account",
		desc: "A username and a password that passes the password rules",
	},
	{
		icon: "fa-shield-halved",
		label: "Assign a role",
		desc: "The role decides what they can chat with, query and open — no role means no access",
	},
	{
		icon: "fa-user-shield",
		label: "Console access",
		desc: "An active admin role makes them staff; with Can manage users they manage accounts too",
	},
	{
		icon: "fa-right-to-bracket",
		label: "They sign in",
		desc: "Switch the account to inactive to block sign-in without deleting it",
	},
];

// Django's AUTH_PASSWORD_VALIDATORS, in words.
const PASSWORD_RULES =
	"8+ characters, not all numbers, not a common password, and not like the username or email.";

// Mirrors engine.services.permissions.PermissionService: what the chosen role
// hands the user, so the admin sees the effect before saving.
function RoleSummary({
	role,
	isSuperuser,
}: {
	role: Role | undefined;
	isSuperuser: boolean;
}) {
	if (isSuperuser) {
		return (
			<div className="role-summary">
				<i className="fa-solid fa-crown role-summary__icon" />
				<div>
					<div className="role-summary__title">Superuser</div>
					<div className="role-summary__desc">
						Full access whatever role is set — the role only takes effect if
						they stop being a superuser.
					</div>
				</div>
			</div>
		);
	}
	if (!role) {
		return (
			<div className="role-summary role-summary--warn">
				<i className="fa-solid fa-circle-exclamation role-summary__icon" />
				<div>
					<div className="role-summary__title">No role</div>
					<div className="role-summary__desc">
						They can sign in, but can't chat, query or open anything.
					</div>
				</div>
			</div>
		);
	}
	if (!role.is_active) {
		return (
			<div className="role-summary role-summary--warn">
				<i className="fa-solid fa-circle-exclamation role-summary__icon" />
				<div>
					<div className="role-summary__title">{role.name} is inactive</div>
					<div className="role-summary__desc">
						It grants nothing until it's switched back on.{" "}
						<Link to={`/admin/roles/${role.id}`}>Open role</Link>
					</div>
				</div>
			</div>
		);
	}
	if (role.is_admin_role) {
		return (
			<div className="role-summary">
				<i className="fa-solid fa-crown role-summary__icon" />
				<div>
					<div className="role-summary__title">{role.name} · Admin role</div>
					<div className="role-summary__desc">
						Console access with every restriction lifted
						{role.can_manage_users ? ", including managing users." : "."}{" "}
						<Link to={`/admin/roles/${role.id}`}>Open role</Link>
					</div>
				</div>
			</div>
		);
	}

	const grants: [number, string, string][] = [
		[role.allowed_databases.length, "database", "databases"],
		[role.allowed_doc_sources.length, "documentation", "documentations"],
		[role.allowed_codebases.length, "codebase", "codebases"],
		[role.allowed_reports.length, "report", "reports"],
		[role.allowed_dashboards.length, "dashboard", "dashboards"],
		[role.allowed_tethers.length, "tether", "tethers"],
		[role.allowed_tools.length, "tool", "tools"],
		[role.allowed_prompts.length, "prompt", "prompts"],
		[role.allowed_mcp_servers.length, "MCP server", "MCP servers"],
	];
	const chips = [
		...(role.can_chat ? ["Chat"] : []),
		`${role.max_row_limit} rows per query`,
		...grants
			.filter(([count]) => count > 0)
			.map(([count, one, many]) => `${count} ${count === 1 ? one : many}`),
	];

	return (
		<div className="role-summary">
			<i className="fa-solid fa-shield-halved role-summary__icon" />
			<div>
				<div className="role-summary__title">{role.name}</div>
				<div className="role-summary__chips">
					{chips.map((chip) => (
						<span key={chip} className="role-chip">
							{chip}
						</span>
					))}
				</div>
				<div className="role-summary__desc">
					<Link to={`/admin/roles/${role.id}`}>Open role</Link>
				</div>
			</div>
		</div>
	);
}

export function UserFormPage() {
	const { id } = useParams();
	const isEdit = Boolean(id);
	const numericId = id ? Number(id) : null;
	const navigate = useNavigate();
	const queryClient = useQueryClient();
	const { user: me } = useAuth();
	const [form, setForm] = useState<UserForm>(EMPTY);
	const [error, setError] = useState<string | null>(null);
	const [howItWorksOpen, setHowItWorksOpen] = useState(false);

	const roles = useQuery({ queryKey: ["admin", "roles"], queryFn: listRoles });
	const existing = useQuery({
		queryKey: ["admin", "users", id],
		queryFn: () => getUser(numericId as number),
		enabled: isEdit,
	});

	useEffect(() => {
		const u = existing.data;
		if (!u) return;
		setForm({
			username: u.username,
			email: u.email,
			password: "",
			confirm_password: "",
			is_active: u.is_active,
			role: u.role ?? "",
		});
	}, [existing.data]);

	function set<K extends keyof UserForm>(key: K, value: UserForm[K]) {
		setForm((f) => ({ ...f, [key]: value }));
	}

	const save = useMutation({
		mutationFn: () => {
			const payload: UserInput = {
				email: form.email,
				is_active: form.is_active,
				role: form.role || null,
			};
			if (!isEdit) payload.username = form.username;
			if (form.password) payload.password = form.password;
			return isEdit
				? updateUser(numericId as number, payload)
				: createUser(payload);
		},
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
			navigate("/admin/users");
		},
		onError: (err) => setError(apiErrorDetail(err, "Save failed.")),
	});

	const passwordMismatch =
		form.confirm_password !== "" && form.password !== form.confirm_password;

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		if (form.password !== form.confirm_password) {
			setError("The two passwords don't match.");
			return;
		}
		save.mutate();
	}

	if (isEdit && existing.isLoading) {
		return (
			<div className="card">
				<p className="text-sec">Loading…</p>
			</div>
		);
	}

	const target = existing.data;
	const isSelf = isEdit && target?.id === me?.id;
	// Only a superuser may change a superuser account (the API enforces it).
	const readOnly = Boolean(target?.is_superuser && !me?.is_superuser);
	const roleList = roles.data?.results ?? [];
	const selectedRole = roleList.find((r) => r.id === form.role);
	const roleOptions = [
		{ value: "", label: "— No role —" },
		...roleList.map((r) => ({
			value: r.id,
			label: r.is_active ? r.name : `${r.name} (inactive)`,
		})),
	];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>
						{!isEdit
							? "Add User"
							: readOnly
								? form.username
								: `Edit ${form.username}`}
					</h1>
					<p>
						{target
							? `Joined ${new Date(target.date_joined).toLocaleDateString()} · ${
									target.last_login
										? `last signed in ${new Date(target.last_login).toLocaleString()}`
										: "never signed in"
								}`
							: "An account that signs in and gets its access from a role"}
					</p>
				</div>
				<div className="form-actions">
					<Link to="/admin/users" className="btn btn-ghost">
						{readOnly ? "Back" : "Cancel"}
					</Link>
					{!readOnly && (
						<button
							type="submit"
							form="user-form"
							className="btn btn-primary"
							disabled={save.isPending}
						>
							{save.isPending
								? "Saving…"
								: isEdit
									? "Save Changes"
									: "Create User"}
						</button>
					)}
				</div>
			</div>

			{readOnly && (
				<div className="flash flash-info" style={{ marginBottom: "var(--md)" }}>
					Read-only. Only a superuser can change a superuser account.
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

			<form id="user-form" className="form-dim-disabled" onSubmit={onSubmit}>
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
					<div className="form-split">
						<div className="wizard-section">
							<WizardSectionHeading step={STEPS[0]} index={0} />
							<div className="card">
								<FormField
									label="Username"
									help={isEdit ? "Usernames can't be changed." : undefined}
								>
									<input
										className="form-control"
										value={form.username}
										required
										disabled={isEdit}
										autoComplete="off"
										onChange={(e) => set("username", e.target.value)}
									/>
								</FormField>
								<FormField label="Email" help="Optional.">
									<input
										className="form-control"
										type="email"
										value={form.email}
										autoComplete="off"
										onChange={(e) => set("email", e.target.value)}
									/>
								</FormField>
								<div className="field-pair">
									<FormField
										label={isEdit ? "New password" : "Password"}
										help={PASSWORD_RULES}
									>
										<input
											className="form-control"
											type="password"
											autoComplete="new-password"
											required={!isEdit}
											placeholder={isEdit ? "Leave blank to keep" : ""}
											value={form.password}
											onChange={(e) => set("password", e.target.value)}
										/>
									</FormField>
									<FormField label="Confirm password">
										<input
											className="form-control"
											type="password"
											autoComplete="new-password"
											required={!isEdit || form.password !== ""}
											aria-invalid={passwordMismatch}
											value={form.confirm_password}
											onChange={(e) => set("confirm_password", e.target.value)}
										/>
										{passwordMismatch && (
											<ul className="errorlist">
												<li>The two passwords don't match.</li>
											</ul>
										)}
									</FormField>
								</div>
							</div>
						</div>

						<div className="wizard-section">
							<WizardSectionHeading step={STEPS[1]} index={1} />
							<div className="card">
								<FormField
									label="Role"
									help={
										isSelf && !me?.is_superuser
											? "You can only move yourself to another admin role that can manage users."
											: undefined
									}
								>
									<CustomSelect
										value={form.role}
										onChange={(v) => set("role", v)}
										options={roleOptions}
									/>
									{!roles.isLoading && (
										<RoleSummary
											role={selectedRole}
											isSuperuser={Boolean(target?.is_superuser)}
										/>
									)}
								</FormField>
								<ToggleField
									label="Is active"
									description={
										isSelf
											? "You can't deactivate your own account."
											: "Only active accounts can sign in. Switch off to block sign-in without deleting the account."
									}
									checked={form.is_active}
									disabled={isSelf}
									onChange={(v) => set("is_active", v)}
								/>
							</div>
						</div>
					</div>
				</fieldset>
			</form>
		</div>
	);
}
