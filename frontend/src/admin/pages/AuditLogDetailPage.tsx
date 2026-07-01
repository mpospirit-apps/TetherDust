import { useQuery } from "@tanstack/react-query";
import type { CSSProperties, ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { getAuditLogEntry } from "../../api/admin";

function MetaItem({ label, children }: { label: string; children: ReactNode }) {
	return (
		<div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
			<span
				style={{
					fontSize: "var(--text-xs)",
					textTransform: "uppercase",
					letterSpacing: 1,
					color: "var(--text-muted)",
					fontWeight: 700,
				}}
			>
				{label}
			</span>
			<span style={{ fontSize: "var(--text-sm)" }}>{children}</span>
		</div>
	);
}

const PRE: CSSProperties = {
	background: "var(--bg-warm, rgba(26,26,26,.04))",
	border: "1px solid var(--border)",
	borderRadius: 8,
	padding: "var(--md)",
	fontSize: 13,
	lineHeight: 1.6,
	whiteSpace: "pre-wrap",
	overflowWrap: "break-word",
	maxHeight: 480,
	overflowY: "auto",
	margin: 0,
};

export function AuditLogDetailPage() {
	const { id } = useParams();
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "audit", id],
		queryFn: () => getAuditLogEntry(id as string),
		enabled: Boolean(id),
	});

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Audit Log</h1>
					<p className="text-mono">{data ? data.id : "Query details"}</p>
				</div>
				<Link to="/admin/audit" className="btn btn-ghost">
					Back
				</Link>
			</div>

			{isLoading ? (
				<div className="card">
					<p className="text-sec">Loading…</p>
				</div>
			) : isError || !data ? (
				<div className="card">
					<p className="text-sec">Failed to load audit log entry.</p>
				</div>
			) : (
				<>
					<div className="card" style={{ marginBottom: "var(--md)" }}>
						<div
							className="flex-gap"
							style={{ gap: "var(--xl)", flexWrap: "wrap" }}
						>
							<MetaItem label="Status">
								{data.success ? (
									<span className="badge badge-success">OK</span>
								) : (
									<span className="badge badge-error">ERROR</span>
								)}
							</MetaItem>
							<MetaItem label="Database">{data.database ?? "—"}</MetaItem>
							<MetaItem label="Rows">{data.row_count ?? "—"}</MetaItem>
							<MetaItem label="Duration">
								{data.execution_time_ms != null
									? `${data.execution_time_ms} ms`
									: "—"}
							</MetaItem>
							<MetaItem label="By">{data.user ?? "—"}</MetaItem>
							<MetaItem label="Time">
								{new Date(data.created_at).toLocaleString()}
							</MetaItem>
						</div>
					</div>

					<div className="card" style={{ marginBottom: "var(--md)" }}>
						<h3 style={{ margin: "0 0 var(--sm)" }}>Query</h3>
						<pre style={PRE}>{data.query}</pre>
					</div>

					{data.error_message && (
						<div className="card">
							<h3 style={{ margin: "0 0 var(--sm)" }}>Error</h3>
							<pre style={{ ...PRE, color: "var(--error, #c0392b)" }}>
								{data.error_message}
							</pre>
						</div>
					)}
				</>
			)}
		</div>
	);
}
