import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { deleteUser, listUsers, type AdminUser } from "../../api/admin";
import { apiErrorDetail } from "../../api/client";

export function UsersPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: listUsers,
  });
  const remove = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
    onError: (err) => window.alert(apiErrorDetail(err, "Delete failed.")),
  });

  function onDelete(user: AdminUser) {
    if (window.confirm(`Delete user "${user.username}"?`)) {
      remove.mutate(user.id);
    }
  }

  const users = data?.results ?? [];

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Users</h1>
          <p>Manage user accounts and role assignments.</p>
        </div>
        <Link to="/admin/users/new" className="btn btn-primary">
          + Add User
        </Link>
      </div>

      <div className="card">
        {isLoading ? (
          <p className="text-sec">Loading…</p>
        ) : isError ? (
          <p className="text-sec">Failed to load users.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Staff</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <strong>{u.username}</strong>
                      {u.is_superuser && (
                        <span className="badge badge-success" style={{ marginLeft: 8 }}>
                          SUPER
                        </span>
                      )}
                    </td>
                    <td className="text-mono">{u.email || "—"}</td>
                    <td>{u.role_name ?? "—"}</td>
                    <td>{u.is_staff ? "Yes" : "No"}</td>
                    <td>
                      {u.is_active ? (
                        <span className="badge badge-success">ACTIVE</span>
                      ) : (
                        <span className="badge badge-muted">INACTIVE</span>
                      )}
                    </td>
                    <td>
                      <div className="flex-gap">
                        <Link to={`/admin/users/${u.id}`} className="btn btn-ghost btn-sm">
                          Edit
                        </Link>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          style={{ color: "var(--danger)" }}
                          onClick={() => onDelete(u)}
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
