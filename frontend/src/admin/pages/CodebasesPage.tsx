import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	type Codebase,
	deleteCodebase,
	listCodebases,
	syncCodebase,
} from "../../api/tethers";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ActionTooltip } from "../components/ActionTooltip";
import {
	DEFAULT_PROVIDER_META,
	PROVIDER_META,
	ProviderGlyph,
} from "../components/providerIcons";

const SYNC_TOOLTIP: Record<string, string> = {
	github:
		"Fetches the latest file tree from GitHub and refreshes the cached listing used for browsing.",
	gitlab:
		"Fetches the latest file tree from GitLab and refreshes the cached listing used for browsing.",
	local: "Rescans the local folder and rebuilds the search index.",
};
const DEFAULT_SYNC_TOOLTIP = "Refreshes this codebase for the agent.";

const TABLE_COLUMNS = 5;

export function CodebasesPage() {
	const queryClient = useQueryClient();
	const [pendingDelete, setPendingDelete] = useState<Codebase | null>(null);
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
		setPendingDelete(c);
	}

	const codebases = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Codebases</h1>
					<p>
						Source code the agent reads on demand — a GitHub or GitLab
						repository (no clone) or a local folder under sources/codebases/
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
							Add a GitHub, GitLab, or local codebase for the agent to browse.
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
									<th>Branch</th>
									<th>Last Synced</th>
									<th>Activity</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{codebases.map((c) => (
									<Fragment key={c.id}>
										<tr>
											<td>
												<div className="db-name-cell">
													<ProviderGlyph
														meta={
															PROVIDER_META[c.provider] ?? DEFAULT_PROVIDER_META
														}
														className="db-name-cell__icon"
													/>
													<div>
														<strong>{c.name}</strong>
														{c.description && (
															<div className="text-sm text-sec truncate">
																{c.description}
															</div>
														)}
													</div>
												</div>
											</td>
											<td className="text-sm">
												{c.provider === "local"
													? "—"
													: c.default_branch || "default"}
											</td>
											<td className="text-sm">
												{c.last_synced_at
													? new Date(c.last_synced_at).toLocaleString()
													: "Never"}
											</td>
											<td>
												{c.is_active ? (
													<span className="badge badge-success">ACTIVE</span>
												) : (
													<span className="badge badge-muted">INACTIVE</span>
												)}
											</td>
											<td>
												<div className="flex-gap">
													<ActionTooltip
														content={
															SYNC_TOOLTIP[c.provider] ?? DEFAULT_SYNC_TOOLTIP
														}
													>
														<button
															type="button"
															className="btn btn-ghost btn-sm"
															onClick={() => sync.mutate(c.id)}
															disabled={c.sync_status === "syncing"}
														>
															{c.sync_status === "syncing" ? (
																<>
																	<i className="fa-solid fa-spinner fa-spin" />{" "}
																	Syncing…
																</>
															) : (
																<>
																	<i className="fa-solid fa-rotate" /> Sync
																</>
															)}
														</button>
													</ActionTooltip>
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
										{c.sync_status === "error" && (
											<tr>
												<td
													colSpan={TABLE_COLUMNS}
													className="db-test-result-cell"
												>
													<div className="flash flash-error">
														Sync failed: {c.sync_error || "Unknown error"}
													</div>
												</td>
											</tr>
										)}
									</Fragment>
								))}
							</tbody>
						</table>
					</div>
				)}
			</div>
			{pendingDelete && (
				<ConfirmDialog
					title="Delete Codebase"
					message={
						<>
							Delete codebase <strong>{pendingDelete.name}</strong>? This cannot
							be undone.
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
