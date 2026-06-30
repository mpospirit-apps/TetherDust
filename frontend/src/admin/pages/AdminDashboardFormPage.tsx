import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { listRoles } from "../../api/admin";
import { apiErrorDetail } from "../../api/client";
import {
	type AdminDashboardInput,
	createDashboard,
	getAdminDashboard,
	updateDashboard,
} from "../../api/dashboards";
import { CheckboxGroup, FormCheckbox, FormField } from "../components/forms";

const REFRESH_INTERVALS: { value: string; label: string }[] = [
	{ value: "5", label: "Every 5 minutes" },
	{ value: "15", label: "Every 15 minutes" },
	{ value: "30", label: "Every 30 minutes" },
	{ value: "60", label: "Every hour" },
	{ value: "360", label: "Every 6 hours" },
	{ value: "720", label: "Every 12 hours" },
	{ value: "1440", label: "Every 24 hours" },
];

interface FormState {
	name: string;
	description: string;
	is_active: boolean;
	auto_refresh: boolean;
	refresh_interval: string;
	allowed_roles: string[];
}

const EMPTY: FormState = {
	name: "",
	description: "",
	is_active: true,
	auto_refresh: false,
	refresh_interval: "",
	allowed_roles: [],
};

export function AdminDashboardFormPage() {
	const { id } = useParams();
	const isEdit = Boolean(id);
	const navigate = useNavigate();
	const queryClient = useQueryClient();

	const [form, setForm] = useState<FormState>(EMPTY);
	const [error, setError] = useState<string | null>(null);

	const roles = useQuery({ queryKey: ["admin", "roles"], queryFn: listRoles });
	const existing = useQuery({
		queryKey: ["admin", "dashboards", id],
		queryFn: () => getAdminDashboard(id as string),
		enabled: isEdit,
	});

	useEffect(() => {
		const d = existing.data;
		if (!d) return;
		setForm({
			name: d.name,
			description: d.description,
			is_active: d.is_active,
			auto_refresh: d.auto_refresh,
			refresh_interval: d.refresh_interval ?? "",
			allowed_roles: d.allowed_roles,
		});
	}, [existing.data]);

	function set<K extends keyof FormState>(key: K, value: FormState[K]) {
		setForm((f) => ({ ...f, [key]: value }));
	}

	const save = useMutation({
		mutationFn: (payload: AdminDashboardInput) =>
			isEdit
				? updateDashboard(id as string, payload)
				: createDashboard(payload),
		onSuccess: (d) => {
			queryClient.invalidateQueries({ queryKey: ["admin", "dashboards"] });
			navigate(`/admin/dashboards/${d.id}`);
		},
		onError: (err) => setError(apiErrorDetail(err, "Save failed.")),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		save.mutate({
			name: form.name,
			description: form.description,
			is_active: form.is_active,
			auto_refresh: form.auto_refresh,
			refresh_interval: form.refresh_interval || null,
			allowed_roles: form.allowed_roles,
		});
	}

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
					<h1>{isEdit ? `Edit ${form.name}` : "New Dashboard"}</h1>
					<p>A dashboard is a grid of D3 charts</p>
				</div>
				<Link to="/admin/dashboards" className="btn btn-ghost">
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
				<FormCheckbox
					label="Auto refresh chart data on a schedule"
					checked={form.auto_refresh}
					onChange={(v) => set("auto_refresh", v)}
				/>
				{form.auto_refresh && (
					<FormField label="Refresh interval">
						<select
							className="form-control"
							value={form.refresh_interval}
							onChange={(e) => set("refresh_interval", e.target.value)}
						>
							<option value="">— Select —</option>
							{REFRESH_INTERVALS.map((r) => (
								<option key={r.value} value={r.value}>
									{r.label}
								</option>
							))}
						</select>
					</FormField>
				)}
				<CheckboxGroup
					label="Allowed roles"
					help="Roles that can view this dashboard (staff always can)."
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
								: "Create Dashboard"}
					</button>
					<Link to="/admin/dashboards" className="btn btn-secondary">
						Cancel
					</Link>
				</div>
			</form>
		</div>
	);
}
