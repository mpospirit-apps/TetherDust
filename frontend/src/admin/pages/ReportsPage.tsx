import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	deleteReport,
	type ExecutionResult,
	listReports,
	type ReportDefinition,
	runReport,
	toggleReport,
} from "../../api/reports";
import { Toggle } from "../components/forms";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const TABLE_COLUMNS = 6;

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

function ReportRow({
	report: r,
	onToggle,
	onDelete,
	onRan,
}: {
	report: ReportDefinition;
	onToggle: (id: string) => void;
	onDelete: (r: ReportDefinition) => void;
	onRan: () => void;
}) {
	const [result, setResult] = useState<ExecutionResult | null>(null);
	const [runError, setRunError] = useState<string | null>(null);

	const run = useMutation({
		mutationFn: () => runReport(r.id),
		onSuccess: (execution) => {
			setRunError(null);
			setResult(execution);
			onRan();
		},
		onError: (err) => {
			setResult(null);
			setRunError(apiErrorDetail(err, "Run failed."));
		},
	});

	return (
		<>
			<tr>
				<td>
					<strong>{r.name}</strong>
					{r.description && (
						<div className="text-sm text-sec truncate">{r.description}</div>
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
					<Toggle
						bare
						checked={r.is_active}
						title={r.is_active ? "Deactivate report" : "Activate report"}
						onChange={() => onToggle(r.id)}
					/>
				</td>
				<td>
					<div className="flex-gap">
						<button
							type="button"
							className="btn btn-ghost btn-sm"
							disabled={run.isPending}
							onClick={() => {
								setResult(null);
								setRunError(null);
								run.mutate();
							}}
						>
							{run.isPending ? (
								<i className="fa-solid fa-spinner fa-spin" />
							) : (
								<>
									<i className="fa-solid fa-play" /> Run
								</>
							)}
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
							onClick={() => onDelete(r)}
						>
							<i className="fa-solid fa-trash" /> Delete
						</button>
					</div>
				</td>
			</tr>
			{(result || runError) && (
				<tr>
					<td colSpan={TABLE_COLUMNS} className="db-test-result-cell">
						<div
							className={
								result?.status === "success"
									? "flash flash-success"
									: "flash flash-error"
							}
						>
							{result?.status === "success" ? (
								<>
									Ran successfully ({result.row_count ?? 0} rows).{" "}
									<Link to={`/admin/report-runs/${result.id}`}>
										View results →
									</Link>
								</>
							) : result?.status === "failed" ? (
								<>
									Failed: {result.error_message || "Unknown error"}.{" "}
									<Link to={`/admin/report-runs/${result.id}`}>View run →</Link>
								</>
							) : (
								`Failed: ${runError}`
							)}
						</div>
					</td>
				</tr>
			)}
		</>
	);
}

export function AdminReportsPage() {
	const queryClient = useQueryClient();
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
					+ Add Report
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
							<i className="fa-solid fa-table-list" />
						</div>
						<h3>No Reports</h3>
						<p className="text-sec">
							Define a SQL report to run on demand or on a schedule.
						</p>
						<Link to="/admin/reports/new" className="btn btn-primary mt-md">
							+ Add Report
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
									<th>Active</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{reports.map((r) => (
									<ReportRow
										key={r.id}
										report={r}
										onToggle={(id) => toggle.mutate(id)}
										onRan={invalidate}
										onDelete={(report) => {
											if (window.confirm(`Delete report "${report.name}"?`))
												remove.mutate(report.id);
										}}
									/>
								))}
							</tbody>
						</table>
					</div>
				)}
			</div>
		</div>
	);
}
