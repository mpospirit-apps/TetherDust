import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	type AdminChart,
	deleteChart,
	getAdminDashboard,
	listCharts,
} from "../../api/dashboards";

export function AdminDashboardDetailPage() {
	const { id } = useParams();
	const dashboardId = id as string;
	const queryClient = useQueryClient();

	const dashboard = useQuery({
		queryKey: ["admin", "dashboards", dashboardId],
		queryFn: () => getAdminDashboard(dashboardId),
	});
	const charts = useQuery({
		queryKey: ["admin", "charts", dashboardId],
		queryFn: () => listCharts(dashboardId),
	});
	const remove = useMutation({
		mutationFn: deleteChart,
		onSuccess: () =>
			queryClient.invalidateQueries({
				queryKey: ["admin", "charts", dashboardId],
			}),
		onError: (err) => window.alert(apiErrorDetail(err, "Delete failed.")),
	});

	function onDelete(c: AdminChart) {
		if (window.confirm(`Delete chart "${c.title}"?`)) {
			remove.mutate(c.id);
		}
	}

	const rows = charts.data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>{dashboard.data?.name ?? "Dashboard"}</h1>
					<p>{dashboard.data?.description || "Charts in this dashboard"}</p>
				</div>
				<div className="flex-gap">
					{dashboard.data && (
						<Link to={`/dashboards/${dashboardId}`} className="btn btn-ghost">
							View dashboard
						</Link>
					)}
					<Link
						to={`/admin/dashboards/${dashboardId}/charts/new`}
						className="btn btn-primary"
					>
						+ Add Chart
					</Link>
				</div>
			</div>

			<div className="card">
				{charts.isLoading ? (
					<p className="text-sec">Loading…</p>
				) : rows.length === 0 ? (
					<div className="empty-state">
						<div className="icon">
							<i className="fa-solid fa-chart-column" />
						</div>
						<h3>No Charts</h3>
						<p className="text-sec">
							Add a chart with a SQL query and D3 code.
						</p>
						<Link
							to={`/admin/dashboards/${dashboardId}/charts/new`}
							className="btn btn-primary mt-md"
						>
							+ Add Chart
						</Link>
					</div>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Title</th>
									<th>Database</th>
									<th>Width</th>
									<th>Status</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{rows.map((c) => (
									<tr key={c.id}>
										<td>
											<strong>{c.title}</strong>
											{c.last_error && (
												<div
													className="text-sm"
													style={{ color: "var(--danger)" }}
												>
													{c.last_error}
												</div>
											)}
										</td>
										<td>
											<span className="type-badge">{c.database_name}</span>
										</td>
										<td>{c.width}/12</td>
										<td>
											{c.is_active ? (
												<span className="badge badge-success">ACTIVE</span>
											) : (
												<span className="badge badge-muted">INACTIVE</span>
											)}
										</td>
										<td>
											<div className="flex-gap">
												<Link
													to={`/admin/dashboards/${dashboardId}/charts/${c.id}`}
													className="btn btn-ghost btn-sm"
												>
													<i className="fa-solid fa-pen" /> Edit
												</Link>
												<button
													type="button"
													className="btn btn-ghost btn-sm"
													style={{ color: "var(--danger)" }}
													onClick={() => onDelete(c)}
												>
													<i className="fa-solid fa-trash" /> Delete
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
