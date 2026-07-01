import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { type DocGenLog, listDocGenLogs } from "../../api/docs";

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

export function DocGenLogsPage() {
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "docgen-logs"],
		queryFn: listDocGenLogs,
	});
	const logs: DocGenLog[] = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Doc Generation</h1>
					<p>History of AI documentation generation runs</p>
				</div>
			</div>

			<div className="card">
				{isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError ? (
					<p className="text-sec">Failed to load generation logs.</p>
				) : logs.length === 0 ? (
					<p className="text-sec">No documentation has been generated yet.</p>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Target</th>
									<th>Type</th>
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
										<td className="text-mono text-sm">
											{log.destination}
											{log.filename ? `/${log.filename}` : ""}
										</td>
										<td>
											<span className="type-badge">
												{log.is_library ? "library" : log.doc_type}
											</span>
										</td>
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
												to={`/admin/docgen-logs/${log.id}`}
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
