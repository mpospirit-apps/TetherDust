import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
	createUser,
	getUser,
	listRoles,
	type UserInput,
	updateUser,
} from "../../api/admin";
import { apiErrorDetail } from "../../api/client";
import { FormCheckbox, FormField } from "../components/forms";

interface UserForm {
	username: string;
	email: string;
	password: string;
	is_active: boolean;
	role: string;
}

const EMPTY: UserForm = {
	username: "",
	email: "",
	password: "",
	is_active: true,
	role: "",
};

export function UserFormPage() {
	const { id } = useParams();
	const isEdit = Boolean(id);
	const numericId = id ? Number(id) : null;
	const navigate = useNavigate();
	const queryClient = useQueryClient();
	const [form, setForm] = useState<UserForm>(EMPTY);
	const [error, setError] = useState<string | null>(null);

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

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		save.mutate();
	}

	if (isEdit && existing.isLoading) {
		return (
			<div className="card">
				<p className="text-sec">Loading…</p>
			</div>
		);
	}

	const roleOptions = roles.data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>{isEdit ? `Edit ${form.username}` : "Add User"}</h1>
					<p>User account and role assignment.</p>
				</div>
				<div className="form-actions">
					<Link to="/admin/users" className="btn btn-ghost">
						Cancel
					</Link>
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

			<form id="user-form" onSubmit={onSubmit}>
				<div className="form-split">
					<div className="card">
						<h3 style={{ margin: "0 0 var(--md)" }}>Account</h3>
						<FormField label="Username">
							<input
								className="form-control"
								value={form.username}
								required
								disabled={isEdit}
								onChange={(e) => set("username", e.target.value)}
							/>
						</FormField>
						<FormField label="Email">
							<input
								className="form-control"
								type="email"
								value={form.email}
								onChange={(e) => set("email", e.target.value)}
							/>
						</FormField>
						<FormField
							label="Password"
							help={isEdit ? "Leave blank to keep existing." : undefined}
						>
							<input
								className="form-control"
								type="password"
								autoComplete="new-password"
								required={!isEdit}
								placeholder={isEdit ? "••••••••  (leave blank to keep)" : ""}
								value={form.password}
								onChange={(e) => set("password", e.target.value)}
							/>
						</FormField>
					</div>

					<div className="card">
						<h3 style={{ margin: "0 0 var(--md)" }}>Access</h3>
						<FormField label="Role">
							<select
								className="form-control"
								value={form.role}
								onChange={(e) => set("role", e.target.value)}
							>
								<option value="">— No role —</option>
								{roleOptions.map((r) => (
									<option key={r.id} value={r.id}>
										{r.name}
									</option>
								))}
							</select>
						</FormField>
						<FormCheckbox
							label="Is active"
							checked={form.is_active}
							onChange={(v) => set("is_active", v)}
						/>
					</div>
				</div>
			</form>
		</div>
	);
}
