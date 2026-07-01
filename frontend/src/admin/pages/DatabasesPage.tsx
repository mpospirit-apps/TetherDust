import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
	type DatabaseConnection,
	deleteDatabase,
	listDatabases,
	type TestResult,
	testDatabase,
} from "../../api/admin";

function TestButton({ id }: { id: string }) {
	const [result, setResult] = useState<TestResult | null>(null);
	const mutation = useMutation({
		mutationFn: () => testDatabase(id),
		onSuccess: setResult,
		onError: () => setResult({ ok: false, detail: "Request failed" }),
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
					<>
						<i className="fa-solid fa-vial" /> Test
					</>
				)}
			</button>
			{result && (
				<span
					className={result.ok ? "badge badge-success" : "badge badge-error"}
				>
					{result.ok ? "Connected ✓" : `Failed: ${result.detail}`}
				</span>
			)}
		</div>
	);
}

export function DatabasesPage() {
	const queryClient = useQueryClient();
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "databases"],
		queryFn: listDatabases,
	});
	const remove = useMutation({
		mutationFn: deleteDatabase,
		onSuccess: () =>
			queryClient.invalidateQueries({ queryKey: ["admin", "databases"] }),
	});

	function onDelete(conn: DatabaseConnection) {
		if (window.confirm(`Delete connection "${conn.name}"?`)) {
			remove.mutate(conn.id);
		}
	}

	const connections = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Database Connections</h1>
					<p>Manage client database connections for MCP tools</p>
				</div>
				<div className="flex-gap">
					<Link to="/admin/databases/new" className="btn btn-primary">
						+ Add Connection
					</Link>
				</div>
			</div>

			<div className="card">
				{isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError ? (
					<p className="text-sec">Failed to load connections.</p>
				) : connections.length === 0 ? (
					<div className="empty-state">
						<div className="icon">
							<i className="fa-solid fa-database" />
						</div>
						<h3>No Databases Configured</h3>
						<p className="text-sec">
							Add a database connection to get started.
						</p>
						<Link to="/admin/databases/new" className="btn btn-primary mt-md">
							+ Add Connection
						</Link>
					</div>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Name</th>
									<th>Engine</th>
									<th>Host</th>
									<th>Database</th>
									<th>Status</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{connections.map((conn) => (
									<tr key={conn.id}>
										<td>
											<strong>{conn.name}</strong>
										</td>
										<td>
											<span className="type-badge">{conn.engine}</span>
										</td>
										<td className="text-mono">{conn.host || "—"}</td>
										<td className="text-mono truncate">{conn.database}</td>
										<td>
											{conn.is_active ? (
												<span className="badge badge-success">ACTIVE</span>
											) : (
												<span className="badge badge-muted">INACTIVE</span>
											)}
										</td>
										<td>
											<div className="flex-gap">
												<TestButton id={conn.id} />
												<Link
													to={`/admin/databases/${conn.id}`}
													className="btn btn-ghost btn-sm"
												>
													<i className="fa-solid fa-pen" /> Edit
												</Link>
												<button
													type="button"
													className="btn btn-ghost btn-sm"
													style={{ color: "var(--danger)" }}
													onClick={() => onDelete(conn)}
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
