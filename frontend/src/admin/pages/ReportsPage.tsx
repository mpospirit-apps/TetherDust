import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	deleteReport,
	listReports,
	type ReportDefinition,
	runReport,
	toggleReport,
} from "../../api/reports";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function scheduleLabel(r: ReportDefinition): string {
	switch (r.schedule_type) {
		case "interval": {
			const m = r.schedule_interval_minutes ?? 0;
			return m % 60 === 0 ? `Every ${m / 60}h` : `Every ${m}m`;
		}
		case "daily":
			return `Daily${r.schedule_time ? ` at ${r.schedule_time.slice(0, 5)}` : ""}`;
		case "weekly":
			return `Weekly${
				r.schedule_day_of_week != null
					? ` on ${WEEKDAYS[r.schedule_day_of_week]}`
					: ""
			}`;
		case "monthly":
			return `Monthly${r.schedule_day_of_month != null ? ` on day ${r.schedule_day_of_month}` : ""}`;
		default:
			return "Manual";
	}
}

export function AdminReportsPage() {
	const queryClient = useQueryClient();
	const navigate = useNavigate();
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "reports"],
		queryFn: listReports,
	});

	function invalidate() {
		void queryClient.invalidateQueries({ queryKey: ["admin", "reports"] });
	}

	const remove = useMutation({
		mutationFn: deleteReport,
		onSuccess: invalidate,
		onError: (err) => window.alert(apiErrorDetail(err, "Delete failed.")),
	});
	const toggle = useMutation({
		mutationFn: toggleReport,
		onSuccess: invalidate,
		onError: (err) => window.alert(apiErrorDetail(err, "Toggle failed.")),
	});
	const run = useMutation({
		mutationFn: runReport,
		onSuccess: (execution) => {
			invalidate();
			navigate(`/admin/report-runs/${execution.id}`);
		},
		onError: (err) => window.alert(apiErrorDetail(err, "Run failed.")),
	});

	const reports = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Reports</h1>
					<p>
						Scheduled SQL reports — run manually or on a schedule, deliver
						in-app or by email
					</p>
				</div>
				<Link to="/admin/reports/new" className="btn btn-primary">
					+ New Report
				</Link>
			</div>

			<div className="card">
				{isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError ? (
					<p className="text-sec">Failed to load reports.</p>
				) : reports.length === 0 ? (
					<div className="empty-state">
						<div className="icon">
							<i className="fa-solid fa-chart-bar" />
						</div>
						<h3>No Reports</h3>
						<p className="text-sec">
							Define a SQL report to run on demand or on a schedule.
						</p>
						<Link to="/admin/reports/new" className="btn btn-primary mt-md">
							+ New Report
						</Link>
					</div>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Name</th>
									<th>Database</th>
									<th>Schedule</th>
									<th>Latest Run</th>
									<th>Status</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{reports.map((r) => (
									<tr key={r.id}>
										<td>
											<strong>{r.name}</strong>
											{r.description && (
												<div className="text-sm text-sec truncate">
													{r.description}
												</div>
											)}
										</td>
										<td>{r.database_name}</td>
										<td>{scheduleLabel(r)}</td>
										<td>
											{r.latest_run ? (
												<span className="text-sm text-sec">
													{new Date(r.latest_run.started_at).toLocaleString()}
												</span>
											) : (
												<span className="text-sm text-sec">—</span>
											)}
										</td>
										<td>
											{r.is_active ? (
												<span className="badge badge-success">ACTIVE</span>
											) : (
												<span className="badge badge-muted">INACTIVE</span>
											)}
										</td>
										<td>
											<div className="flex-gap">
												<button
													type="button"
													className="btn btn-ghost btn-sm"
													onClick={() => run.mutate(r.id)}
													disabled={run.isPending}
												>
													<i className="fa-solid fa-play" /> Run
												</button>
												<button
													type="button"
													className="btn btn-ghost btn-sm"
													onClick={() => toggle.mutate(r.id)}
												>
													<i
														className={`fa-solid ${r.is_active ? "fa-toggle-off" : "fa-toggle-on"}`}
													/>{" "}
													{r.is_active ? "Deactivate" : "Activate"}
												</button>
												<Link
													to={`/admin/reports/${r.id}`}
													className="btn btn-ghost btn-sm"
												>
													<i className="fa-solid fa-pen" /> Edit
												</Link>
												<button
													type="button"
													className="btn btn-ghost btn-sm"
													style={{ color: "var(--danger)" }}
													onClick={() => {
														if (window.confirm(`Delete report "${r.name}"?`))
															remove.mutate(r.id);
													}}
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
