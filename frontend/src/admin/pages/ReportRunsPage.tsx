import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listExecutions, type ReportExecutionRow } from "../../api/reports";

function StatusBadge({ status }: { status: ReportExecutionRow["status"] }) {
	if (status === "success")
		return <span className="badge badge-success">SUCCESS</span>;
	if (status === "failed")
		return <span className="badge badge-error">FAILED</span>;
	return <span className="badge badge-muted">RUNNING</span>;
}

export function ReportRunsPage() {
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "report-executions"],
		queryFn: () => listExecutions(),
		refetchInterval: 10_000,
	});

	const executions = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Report Runs</h1>
					<p>Recent report executions — manual and scheduled</p>
				</div>
			</div>

			<div className="card">
				{isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError ? (
					<p className="text-sec">Failed to load executions.</p>
				) : executions.length === 0 ? (
					<div className="empty-state">
						<div className="icon">
							<i className="fa-solid fa-clock-rotate-left" />
						</div>
						<h3>No Runs Yet</h3>
						<p className="text-sec">Run a report to see executions here.</p>
					</div>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Report</th>
									<th>Status</th>
									<th>Started</th>
									<th>Duration</th>
									<th>Rows</th>
									<th>Triggered By</th>
									<th />
								</tr>
							</thead>
							<tbody>
								{executions.map((ex) => (
									<tr key={ex.id}>
										<td>
											<strong>{ex.report_name}</strong>
										</td>
										<td>
											<StatusBadge status={ex.status} />
										</td>
										<td className="text-sm">
											{new Date(ex.started_at).toLocaleString()}
										</td>
										<td>
											{ex.execution_time_ms != null
												? `${ex.execution_time_ms}ms`
												: "—"}
										</td>
										<td>{ex.row_count ?? "—"}</td>
										<td className="text-sm text-sec">
											{ex.triggered_by ?? "Scheduled"}
										</td>
										<td>
											<Link
												to={`/admin/report-runs/${ex.id}`}
												className="btn btn-ghost btn-sm"
											>
												<i className="fa-solid fa-eye" /> View
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
