import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { type ChartGenLog, listChartGenLogs } from "../../api/dashboards";

function statusBadge(status: string): string {
	if (status === "success") return "badge badge-success";
	if (status === "partial") return "badge badge-orange";
	if (status === "failed") return "badge badge-error";
	return "badge badge-muted";
}

function fmtDate(iso: string | null): string {
	if (!iso) return "—";
	return new Date(iso).toLocaleString();
}

function fmtDuration(ms: number | null): string {
	if (ms == null) return "—";
	if (ms < 1000) return `${ms} ms`;
	return `${(ms / 1000).toFixed(1)} s`;
}

export function ChartGenLogsPage() {
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "chartgen-logs"],
		queryFn: listChartGenLogs,
	});
	const logs: ChartGenLog[] = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Chart Generation</h1>
					<p>History of AI dashboard generation runs</p>
				</div>
			</div>

			<div className="card">
				{isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError ? (
					<p className="text-sec">Failed to load generation logs.</p>
				) : logs.length === 0 ? (
					<p className="text-sec">No dashboards have been generated yet.</p>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Dashboard</th>
									<th>Charts</th>
									<th>Status</th>
									<th>Duration</th>
									<th>By</th>
									<th>Started</th>
									<th />
								</tr>
							</thead>
							<tbody>
								{logs.map((log) => (
									<tr key={log.id}>
										<td>
											<strong>{log.dashboard_name}</strong>
										</td>
										<td>{log.charts_created ?? "—"}</td>
										<td>
											<span className={statusBadge(log.status)}>
												{log.status.toUpperCase()}
											</span>
											{log.status === "failed" && log.error_message && (
												<div className="text-sm text-sec truncate">
													{log.error_message}
												</div>
											)}
										</td>
										<td>{fmtDuration(log.execution_time_ms)}</td>
										<td>{log.user ?? "—"}</td>
										<td className="text-sm">{fmtDate(log.started_at)}</td>
										<td>
											<Link
												to={`/admin/chartgen-logs/${log.id}`}
												className="btn btn-ghost btn-sm"
											>
												View
											</Link>
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
