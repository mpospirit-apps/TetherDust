import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
	type AdminUser,
	deleteUser,
	listUsers,
	updateUser,
} from "../../api/admin";
import { apiErrorDetail } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { Toggle } from "../components/forms";

// What a user can actually reach, worked out the way the backend does: a
// superuser or staff (an active admin role) gets the console; otherwise an
// active role is what grants anything at all.
function accessBadge(u: AdminUser) {
	if (u.is_superuser) {
		return <span className="badge badge-success">Superuser</span>;
	}
	if (u.is_staff) return <span className="badge badge-info">Admin</span>;
	if (u.role && u.role_is_active) {
		return <span className="badge badge-muted">Member</span>;
	}
	return (
		<span
			className="badge badge-orange"
			title={
				u.role
					? "Their role is inactive, so it grants nothing."
					: "Without a role they can sign in but can't use anything."
			}
		>
			No access
		</span>
	);
}

export function UsersPage() {
	const queryClient = useQueryClient();
	const { user: me } = useAuth();
	const canManage = me?.can_manage_users ?? false;
	const [pendingDelete, setPendingDelete] = useState<AdminUser | null>(null);

	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "users"],
		queryFn: listUsers,
		enabled: canManage,
	});
	const invalidate = () =>
		queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
	const remove = useMutation({
		mutationFn: deleteUser,
		onSuccess: invalidate,
		onError: (err) => window.alert(apiErrorDetail(err, "Delete failed.")),
	});
	const setActive = useMutation({
		mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
			updateUser(id, { is_active }),
		onSuccess: invalidate,
		onError: (err) => window.alert(apiErrorDetail(err, "Update failed.")),
	});

	const users = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Users</h1>
					<p>
						People who can sign in, and the role each one gets their access from
					</p>
				</div>
				{canManage && (
					<Link to="/admin/users/new" className="btn btn-primary">
						+ Add User
					</Link>
				)}
			</div>

			<div className="card">
				{!canManage ? (
					<div className="empty-state">
						<div className="icon">
							<i className="fa-solid fa-lock" />
						</div>
						<h3>User management is restricted</h3>
						<p className="text-sec">
							Seeing and changing accounts needs "Can manage users" on your
							role. Ask a superuser or another user admin to grant it.
						</p>
					</div>
				) : isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError ? (
					<p className="text-sec">Failed to load users.</p>
				) : users.length === 0 ? (
					<div className="empty-state">
						<div className="icon">
							<i className="fa-solid fa-users" />
						</div>
						<h3>No Users</h3>
						<p className="text-sec">Add an account and give it a role.</p>
						<Link to="/admin/users/new" className="btn btn-primary mt-md">
							+ Add User
						</Link>
					</div>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>User</th>
									<th>Role</th>
									<th>Access</th>
									<th>Last Sign-in</th>
									<th>Active</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{users.map((u) => {
									const isSelf = u.id === me?.id;
									// Only a superuser may change a superuser account.
									const locked = u.is_superuser && !me?.is_superuser;
									return (
										<tr key={u.id}>
											<td>
												<div className="user-cell">
													<span
														className="user-cell__avatar"
														aria-hidden="true"
													>
														{u.username.charAt(0).toUpperCase()}
													</span>
													<div className="user-cell__body">
														<div className="user-cell__name">
															<strong>{u.username}</strong>
															{isSelf && (
																<span className="badge badge-info">You</span>
															)}
														</div>
														<div className="user-cell__email">
															{u.email || "No email"}
														</div>
													</div>
												</div>
											</td>
											<td>
												{u.role ? (
													<div className="flex-gap">
														<Link to={`/admin/roles/${u.role}`}>
															{u.role_name}
														</Link>
														{!u.role_is_active && (
															<span className="badge badge-muted">
																Inactive
															</span>
														)}
													</div>
												) : (
													<span className="text-sec">No role</span>
												)}
											</td>
											<td>{accessBadge(u)}</td>
											<td className="text-sec">
												{u.last_login
													? new Date(u.last_login).toLocaleString()
													: "Never"}
											</td>
											<td>
												<Toggle
													bare
													checked={u.is_active}
													disabled={isSelf || locked || setActive.isPending}
													title={
														isSelf
															? "You can't deactivate your own account"
															: locked
																? "Only a superuser can change a superuser"
																: u.is_active
																	? "Deactivate — blocks sign-in"
																	: "Activate — allows sign-in"
													}
													onChange={(v) =>
														setActive.mutate({ id: u.id, is_active: v })
													}
												/>
											</td>
											<td>
												<div className="flex-gap">
													<Link
														to={`/admin/users/${u.id}`}
														className="btn btn-ghost btn-sm"
													>
														<i
															className={`fa-solid ${locked ? "fa-eye" : "fa-pen"}`}
														/>{" "}
														{locked ? "View" : "Edit"}
													</Link>
													{!isSelf && !locked && (
														<button
															type="button"
															className="btn btn-ghost btn-sm"
															style={{ color: "var(--danger)" }}
															onClick={() => setPendingDelete(u)}
														>
															<i className="fa-solid fa-trash" /> Delete
														</button>
													)}
												</div>
											</td>
										</tr>
									);
								})}
							</tbody>
						</table>
					</div>
				)}
			</div>

			{pendingDelete && (
				<ConfirmDialog
					title="Delete User"
					message={
						<>
							Delete <strong>{pendingDelete.username}</strong>? Their chat
							history goes with the account. To only block sign-in, switch them
							to inactive instead.
						</>
					}
					onConfirm={() => {
						remove.mutate(pendingDelete.id);
						setPendingDelete(null);
					}}
					onCancel={() => setPendingDelete(null)}
				/>
			)}
		</div>
	);
}
