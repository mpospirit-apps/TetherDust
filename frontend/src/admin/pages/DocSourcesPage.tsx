import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	type DocSource,
	type DocSourceValidation,
	deleteDocSource,
	listDocSources,
	validateDocSource,
} from "../../api/docs";
import { AlertDialog } from "../../components/AlertDialog";
import { ConfirmDialog } from "../../components/ConfirmDialog";

const TABLE_COLUMNS = 4;

function flashClass(level: DocSourceValidation["level"]): string {
	if (level === "success") return "flash flash-success";
	if (level === "warning") return "flash flash-warning";
	return "flash flash-error";
}

function DocSourceRow({
	src,
	onDelete,
}: {
	src: DocSource;
	onDelete: (src: DocSource) => void;
}) {
	const [result, setResult] = useState<DocSourceValidation | null>(null);
	const validate = useMutation({
		mutationFn: () => validateDocSource(src.id),
		onSuccess: setResult,
		onError: () =>
			setResult({ ok: false, level: "error", message: "Request failed" }),
	});

	return (
		<>
			<tr>
				<td>
					<strong>{src.folder_name}</strong>
					{src.description && (
						<div className="text-sm text-sec truncate">{src.description}</div>
					)}
				</td>
				<td>
					<span className="type-badge">{src.doc_type_display}</span>
				</td>
				<td>
					{src.is_active ? (
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
							disabled={validate.isPending}
							onClick={() => {
								setResult(null);
								validate.mutate();
							}}
						>
							{validate.isPending ? (
								<i className="fa-solid fa-spinner fa-spin" />
							) : (
								<>
									<i className="fa-solid fa-check-double" /> Validate
								</>
							)}
						</button>
						<Link
							to={`/admin/docsources/${src.id}`}
							className="btn btn-ghost btn-sm"
						>
							<i className="fa-solid fa-pen" /> Edit
						</Link>
						<button
							type="button"
							className="btn btn-ghost btn-sm"
							style={{ color: "var(--danger)" }}
							onClick={() => onDelete(src)}
						>
							<i className="fa-solid fa-trash" /> Delete
						</button>
					</div>
				</td>
			</tr>
			{result && (
				<tr>
					<td colSpan={TABLE_COLUMNS} className="db-test-result-cell">
						<div className={flashClass(result.level)}>
							{result.message}
							{result.last_modified ? ` · ${result.last_modified}` : ""}
						</div>
					</td>
				</tr>
			)}
		</>
	);
}

export function DocSourcesPage() {
	const queryClient = useQueryClient();
	const [pendingDelete, setPendingDelete] = useState<DocSource | null>(null);
	const [deleteError, setDeleteError] = useState<string | null>(null);
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "docsources"],
		queryFn: listDocSources,
	});
	const remove = useMutation({
		mutationFn: deleteDocSource,
		onSuccess: () =>
			queryClient.invalidateQueries({ queryKey: ["admin", "docsources"] }),
		onError: (err) => setDeleteError(apiErrorDetail(err, "Delete failed.")),
	});

	function onDelete(src: DocSource) {
		setPendingDelete(src);
	}

	const sources = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Documentation</h1>
					<p>
						Folders under /sources/docs/ exposed to the agent and the docs
						viewer
					</p>
				</div>
				<Link to="/admin/docsources/add" className="btn btn-primary">
					+ Add Documentation
				</Link>
			</div>

			<div className="card">
				{isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError ? (
					<p className="text-sec">Failed to load documentation sources.</p>
				) : sources.length === 0 ? (
					<div className="empty-state">
						<div className="icon">
							<i className="fa-solid fa-book" />
						</div>
						<h3>No Documentation Sources</h3>
						<p className="text-sec">
							Drop a folder under /sources/docs/ or generate documentation with
							AI.
						</p>
						<Link to="/admin/docsources/add" className="btn btn-primary mt-md">
							+ Add Documentation
						</Link>
					</div>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Folder</th>
									<th>Type</th>
									<th>Status</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{sources.map((src) => (
									<DocSourceRow key={src.id} src={src} onDelete={onDelete} />
								))}
							</tbody>
						</table>
					</div>
				)}
			</div>
			{pendingDelete && (
				<ConfirmDialog
					title="Delete Documentation Source"
					message={
						<>
							Delete documentation source{" "}
							<strong>{pendingDelete.folder_name}</strong>? Its folder must
							already be deleted from disk under sources/docs/ — if it still
							exists, this will fail and tell you to remove it first.
						</>
					}
					onConfirm={() => {
						remove.mutate(pendingDelete.id);
						setPendingDelete(null);
					}}
					onCancel={() => setPendingDelete(null)}
				/>
			)}
			{deleteError && (
				<AlertDialog
					title="Delete Failed"
					message={deleteError}
					onClose={() => setDeleteError(null)}
				/>
			)}
		</div>
	);
}
