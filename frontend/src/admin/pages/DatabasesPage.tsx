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
import { ConfirmDialog } from "../../components/ConfirmDialog";
import {
	DEFAULT_ENGINE_META,
	ENGINE_META,
	EngineIconGlyph,
} from "../components/engineIcons";

const TABLE_COLUMNS = 5;

function DatabaseRow({
	conn,
	onDelete,
}: {
	conn: DatabaseConnection;
	onDelete: (conn: DatabaseConnection) => void;
}) {
	const [result, setResult] = useState<TestResult | null>(null);
	const test = useMutation({
		mutationFn: () => testDatabase(conn.id),
		onSuccess: setResult,
		onError: () => setResult({ ok: false, detail: "Request failed" }),
	});

	const engineMeta = ENGINE_META[conn.engine] ?? DEFAULT_ENGINE_META;

	return (
		<>
			<tr>
				<td>
					<div className="db-name-cell">
						<EngineIconGlyph
							icon={engineMeta.icon}
							className="db-name-cell__icon"
						/>
						<strong>{conn.name}</strong>
					</div>
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
						<button
							type="button"
							className="btn btn-ghost btn-sm"
							disabled={test.isPending}
							onClick={() => {
								setResult(null);
								test.mutate();
							}}
						>
							{test.isPending ? (
								<i className="fa-solid fa-spinner fa-spin" />
							) : (
								<>
									<i className="fa-solid fa-plug-circle-check" /> Test
								</>
							)}
						</button>
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
			{result && (
				<tr>
					<td colSpan={TABLE_COLUMNS} className="db-test-result-cell">
						<div
							className={
								result.ok ? "flash flash-success" : "flash flash-error"
							}
						>
							{result.ok ? "Connected ✓" : `Failed: ${result.detail}`}
						</div>
					</td>
				</tr>
			)}
		</>
	);
}

export function DatabasesPage() {
	const queryClient = useQueryClient();
	const [pendingDelete, setPendingDelete] = useState<DatabaseConnection | null>(
		null,
	);
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
		setPendingDelete(conn);
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
									<th>Host</th>
									<th>Database</th>
									<th>Status</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{connections.map((conn) => (
									<DatabaseRow key={conn.id} conn={conn} onDelete={onDelete} />
								))}
							</tbody>
						</table>
					</div>
				)}
			</div>
			{pendingDelete && (
				<ConfirmDialog
					title="Delete Database Connection"
					message={
						<>
							Delete connection <strong>{pendingDelete.name}</strong>? This
							cannot be undone.
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
