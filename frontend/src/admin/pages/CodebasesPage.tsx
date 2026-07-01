import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	type Codebase,
	deleteCodebase,
	listCodebases,
	type SyncStatus,
	syncCodebase,
} from "../../api/tethers";

function SyncBadge({ status, error }: { status: SyncStatus; error: string }) {
	switch (status) {
		case "ok":
			return <span className="badge badge-success">SYNCED</span>;
		case "syncing":
			return (
				<span className="badge badge-muted">
					<i className="fa-solid fa-spinner fa-spin" /> SYNCING
				</span>
			);
		case "error":
			return (
				<span className="badge badge-error" title={error}>
					ERROR
				</span>
			);
		default:
			return <span className="badge badge-muted">PENDING</span>;
	}
}

export function CodebasesPage() {
	const queryClient = useQueryClient();
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "codebases"],
		queryFn: listCodebases,
		refetchInterval: (query) =>
			(query.state.data?.results ?? []).some((c) => c.sync_status === "syncing")
				? 3000
				: false,
	});

	function invalidate() {
		void queryClient.invalidateQueries({ queryKey: ["admin", "codebases"] });
	}

	const remove = useMutation({
		mutationFn: deleteCodebase,
		onSuccess: invalidate,
		onError: (err) => window.alert(apiErrorDetail(err, "Delete failed.")),
	});
	const sync = useMutation({
		mutationFn: syncCodebase,
		onSuccess: invalidate,
		onError: (err) => window.alert(apiErrorDetail(err, "Sync failed.")),
	});

	function onDelete(c: Codebase) {
		if (window.confirm(`Delete codebase "${c.name}"?`)) remove.mutate(c.id);
	}

	const codebases = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Codebases</h1>
					<p>
						Source repositories the agent reads on demand (GitHub, no clone)
					</p>
				</div>
				<Link to="/admin/codebases/new" className="btn btn-primary">
					+ Add Codebase
				</Link>
			</div>

			<div className="card">
				{isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError ? (
					<p className="text-sec">Failed to load codebases.</p>
				) : codebases.length === 0 ? (
					<div className="empty-state">
						<div className="icon">
							<i className="fa-solid fa-code-branch" />
						</div>
						<h3>No Codebases</h3>
						<p className="text-sec">
							Add a GitHub repository for the agent to browse.
						</p>
						<Link to="/admin/codebases/new" className="btn btn-primary mt-md">
							+ Add Codebase
						</Link>
					</div>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Name</th>
									<th>Repository</th>
									<th>Branch</th>
									<th>Sync</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{codebases.map((c) => (
									<tr key={c.id}>
										<td>
											<strong>{c.name}</strong>
											{c.description && (
												<div className="text-sm text-sec truncate">
													{c.description}
												</div>
											)}
										</td>
										<td className="text-sm">{c.repo_url}</td>
										<td className="text-sm">
											{c.branch || c.default_branch || "default"}
										</td>
										<td>
											<SyncBadge status={c.sync_status} error={c.sync_error} />
										</td>
										<td>
											<div className="flex-gap">
												<button
													type="button"
													className="btn btn-ghost btn-sm"
													onClick={() => sync.mutate(c.id)}
													disabled={c.sync_status === "syncing"}
												>
													<i className="fa-solid fa-rotate" /> Sync
												</button>
												<Link
													to={`/admin/codebases/${c.id}`}
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
