import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	getAdminTether,
	getTetherStatus,
	getTetherVersions,
	regenerateTether,
	type TetherVersionRow,
} from "../../api/tethers";

function VersionStatus({ status }: { status: string }) {
	if (status === "success")
		return <span className="badge badge-success">SUCCESS</span>;
	if (status === "failed")
		return <span className="badge badge-error">FAILED</span>;
	return <span className="badge badge-muted">RUNNING</span>;
}

export function TetherDetailPage() {
	const { id } = useParams();
	const tetherId = id as string;
	const queryClient = useQueryClient();

	const tether = useQuery({
		queryKey: ["admin", "tethers", tetherId],
		queryFn: () => getAdminTether(tetherId),
	});
	const status = useQuery({
		queryKey: ["admin", "tether-status", tetherId],
		queryFn: () => getTetherStatus(tetherId),
		refetchInterval: (query) =>
			query.state.data?.status === "running" ? 2500 : false,
	});
	const versions = useQuery({
		queryKey: ["admin", "tether-versions", tetherId],
		queryFn: () => getTetherVersions(tetherId),
		refetchInterval: () => (status.data?.status === "running" ? 2500 : false),
	});

	const regenerate = useMutation({
		mutationFn: () => regenerateTether(tetherId),
		onSuccess: () => {
			void queryClient.invalidateQueries({
				queryKey: ["admin", "tether-status", tetherId],
			});
			void queryClient.invalidateQueries({
				queryKey: ["admin", "tether-versions", tetherId],
			});
		},
		onError: (err) => window.alert(apiErrorDetail(err, "Regenerate failed.")),
	});

	const running = status.data?.status === "running";
	const rows: TetherVersionRow[] = versions.data?.versions ?? [];

	if (tether.isLoading) {
		return (
			<div className="card">
				<p className="text-sec">Loading…</p>
			</div>
		);
	}
	if (tether.isError || !tether.data) {
		return <p className="text-sec">Failed to load tether.</p>;
	}
	const t = tether.data;

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>{t.name}</h1>
					<p className="text-sec">
						{t.source_name} ↔ {t.database_name}
					</p>
				</div>
				<div className="flex-gap">
					<Link to={`/tethers/${t.id}`} className="btn btn-secondary">
						<i className="fa-solid fa-diagram-project" /> Open viewer
					</Link>
					<Link to={`/admin/tethers/${t.id}/edit`} className="btn btn-ghost">
						Edit
					</Link>
					<button
						type="button"
						className="btn btn-primary"
						disabled={running || regenerate.isPending}
						onClick={() => regenerate.mutate()}
					>
						<i className="fa-solid fa-wand-magic-sparkles" />{" "}
						{running ? "Generating…" : "Regenerate"}
					</button>
				</div>
			</div>

			{t.description && <p className="text-sec">{t.description}</p>}

			{running && (
				<div className="card" style={{ marginBottom: "var(--md)" }}>
					<h3 style={{ marginBottom: "var(--sm)" }}>
						<i className="fa-solid fa-spinner fa-spin" /> Generating version{" "}
						{status.data?.version_number}
					</h3>
					<pre
						style={{
							background: "var(--bg-warm)",
							padding: "var(--md)",
							borderRadius: "8px",
							maxHeight: 240,
							overflow: "auto",
							whiteSpace: "pre-wrap",
							fontSize: "12px",
						}}
					>
						{status.data?.agent_output || "Starting agent…"}
					</pre>
				</div>
			)}

			<div className="card">
				<h3 style={{ marginBottom: "var(--md)" }}>Versions</h3>
				{rows.length === 0 ? (
					<p className="text-sec">No versions yet.</p>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Version</th>
									<th>Status</th>
									<th>Started</th>
									<th>Duration</th>
									<th>Triggered By</th>
									<th />
								</tr>
							</thead>
							<tbody>
								{rows.map((v) => (
									<tr key={v.id}>
										<td>
											v{v.version_number}
											{v.is_current && (
												<span
													className="badge badge-success"
													style={{ marginLeft: 6 }}
												>
													CURRENT
												</span>
											)}
										</td>
										<td>
											<VersionStatus status={v.status} />
											{v.status === "failed" && v.error_message && (
												<div
													className="text-sm text-sec truncate"
													title={v.error_message}
												>
													{v.error_message}
												</div>
											)}
										</td>
										<td className="text-sm">
											{new Date(v.started_at).toLocaleString()}
										</td>
										<td>
											{v.execution_time_ms != null
												? `${v.execution_time_ms}ms`
												: "—"}
										</td>
										<td className="text-sm text-sec">
											{v.triggered_by ?? "—"}
										</td>
										<td>
											{v.is_current && (
												<Link
													to={`/tethers/${t.id}`}
													className="btn btn-ghost btn-sm"
												>
													<i className="fa-solid fa-eye" /> View
												</Link>
											)}
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
