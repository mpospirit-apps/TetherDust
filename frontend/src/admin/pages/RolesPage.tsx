import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { deleteRole, listRoles, type Role } from "../../api/admin";
import { apiErrorDetail } from "../../api/client";

export function RolesPage() {
	const queryClient = useQueryClient();
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "roles"],
		queryFn: listRoles,
	});
	const remove = useMutation({
		mutationFn: deleteRole,
		onSuccess: () =>
			queryClient.invalidateQueries({ queryKey: ["admin", "roles"] }),
		onError: (err) => window.alert(apiErrorDetail(err, "Delete failed.")),
	});

	function onDelete(role: Role) {
		if (window.confirm(`Delete role "${role.name}"?`)) {
			remove.mutate(role.id);
		}
	}

	const roles = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Roles</h1>
					<p>Define what each role can access.</p>
				</div>
				<Link to="/admin/roles/new" className="btn btn-primary">
					+ Add Role
				</Link>
			</div>

			<div className="card">
				{isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError ? (
					<p className="text-sec">Failed to load roles.</p>
				) : roles.length === 0 ? (
					<div className="empty-state">
						<div className="icon">
							<i className="fa-solid fa-shield-halved" />
						</div>
						<h3>No roles yet</h3>
						<p className="text-sec">Create a role to assign to users.</p>
						<Link to="/admin/roles/new" className="btn btn-primary mt-md">
							+ Add Role
						</Link>
					</div>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Name</th>
									<th>Type</th>
									<th>Chat</th>
									<th>Status</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{roles.map((r) => (
									<tr key={r.id}>
										<td>
											<strong>{r.name}</strong>
											{r.description && (
												<div className="text-sec">{r.description}</div>
											)}
										</td>
										<td>
											{r.is_admin_role ? (
												<span className="badge badge-success">ADMIN</span>
											) : (
												<span className="type-badge">Standard</span>
											)}
										</td>
										<td>{r.can_chat ? "Yes" : "No"}</td>
										<td>
											{r.is_active ? (
												<span className="badge badge-success">ACTIVE</span>
											) : (
												<span className="badge badge-muted">INACTIVE</span>
											)}
										</td>
										<td>
											<div className="flex-gap">
												<Link
													to={`/admin/roles/${r.id}`}
													className="btn btn-ghost btn-sm"
												>
													Edit
												</Link>
												<button
													type="button"
													className="btn btn-ghost btn-sm"
													style={{ color: "var(--danger)" }}
													onClick={() => onDelete(r)}
												>
													Delete
												</button>
											</div>
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				)}
			</div>
		</div>
	);
}
