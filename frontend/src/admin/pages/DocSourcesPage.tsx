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

function badgeClass(level: DocSourceValidation["level"]): string {
	if (level === "success") return "badge badge-success";
	if (level === "warning") return "badge badge-orange";
	return "badge badge-error";
}

function ValidateButton({ id }: { id: string }) {
	const [result, setResult] = useState<DocSourceValidation | null>(null);
	const mutation = useMutation({
		mutationFn: () => validateDocSource(id),
		onSuccess: setResult,
		onError: () =>
			setResult({ ok: false, level: "error", message: "Request failed" }),
	});
	return (
		<div className="db-test">
			<button
				type="button"
				className="btn btn-ghost btn-sm"
				disabled={mutation.isPending}
				onClick={() => mutation.mutate()}
			>
				{mutation.isPending ? (
					<i className="fa-solid fa-spinner fa-spin" />
				) : (
					"Validate"
				)}
			</button>
			{result && (
				<span className={badgeClass(result.level)}>
					{result.message}
					{result.last_modified ? ` · ${result.last_modified}` : ""}
				</span>
			)}
		</div>
	);
}

export function DocSourcesPage() {
	const queryClient = useQueryClient();
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "docsources"],
		queryFn: listDocSources,
	});
	const remove = useMutation({
		mutationFn: deleteDocSource,
		onSuccess: () =>
			queryClient.invalidateQueries({ queryKey: ["admin", "docsources"] }),
		onError: (err) => window.alert(apiErrorDetail(err, "Delete failed.")),
	});

	function onDelete(src: DocSource) {
		if (
			window.confirm(
				`Delete documentation source "${src.folder_name}"? This also removes its folder on disk.`,
			)
		) {
			remove.mutate(src.id);
		}
	}

	const sources = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Documentation</h1>
					<p>
						Folders under documentations/ exposed to the agent and the docs
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
							Register a folder or generate documentation with AI.
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
									<th>Patterns</th>
									<th>Status</th>
									<th>Validate</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{sources.map((src) => (
									<tr key={src.id}>
										<td>
											<strong>{src.folder_name}</strong>
											{src.description && (
												<div className="text-sm text-sec truncate">
													{src.description}
												</div>
											)}
										</td>
										<td>
											<span className="type-badge">{src.doc_type_display}</span>
										</td>
										<td className="text-mono text-sm">
											{(src.file_patterns?.length
												? src.file_patterns
												: ["*.md"]
											).join(", ")}
										</td>
										<td>
											{src.is_active ? (
												<span className="badge badge-success">ACTIVE</span>
											) : (
												<span className="badge badge-muted">INACTIVE</span>
											)}
										</td>
										<td>
											<ValidateButton id={src.id} />
										</td>
										<td>
											<div className="flex-gap">
												<Link
													to={`/admin/docsources/${src.id}`}
													className="btn btn-ghost btn-sm"
												>
													Edit
												</Link>
												<button
													type="button"
													className="btn btn-ghost btn-sm"
													style={{ color: "var(--danger)" }}
													onClick={() => onDelete(src)}
												>
													Delete
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
