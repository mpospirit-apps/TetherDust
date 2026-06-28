import { useQuery } from "@tanstack/react-query";
import type { CSSProperties, ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { getDocGenLog } from "../../api/docs";

function statusBadge(status: string): string {
	if (status === "success") return "badge badge-success";
	if (status === "partial") return "badge badge-orange";
	if (status === "failed") return "badge badge-error";
	return "badge badge-muted";
}

function fmtDate(iso: string | null): string {
	return iso ? new Date(iso).toLocaleString() : "—";
}

function fmtDuration(ms: number | null): string {
	if (ms == null) return "—";
	return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function fmtBytes(n: number | null): string {
	if (n == null) return "—";
	if (n < 1024) return `${n} B`;
	if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
	return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

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

function Chips({ items }: { items: string[] }) {
	return (
		<div className="flex-gap" style={{ flexWrap: "wrap" }}>
			{items.map((it) => (
				<span key={it} className="badge badge-muted">
					{it}
				</span>
			))}
		</div>
	);
}

export function DocGenLogDetailPage() {
	const { id } = useParams();
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "docgen-logs", id],
		queryFn: () => getDocGenLog(id as string),
		enabled: Boolean(id),
	});

	const target = data
		? data.is_library
			? `${data.destination}/ (library)`
			: `${data.destination}${data.filename ? `/${data.filename}` : ""}`
		: "Generation run";

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Doc Generation</h1>
					<p className="text-mono">{target}</p>
				</div>
				<Link to="/admin/docgen-logs" className="btn btn-ghost">
					Back
				</Link>
			</div>

			{isLoading ? (
				<div className="card">
					<p className="text-sec">Loading…</p>
				</div>
			) : isError || !data ? (
				<div className="card">
					<p className="text-sec">Failed to load generation log.</p>
				</div>
			) : (
				<>
					<div className="card" style={{ marginBottom: "var(--md)" }}>
						<div
							className="flex-gap"
							style={{ gap: "var(--xl)", flexWrap: "wrap" }}
						>
							<MetaItem label="Status">
								<span className={statusBadge(data.status)}>
									{data.status.toUpperCase()}
								</span>
							</MetaItem>
							<MetaItem label="Type">
								{data.is_library ? "library" : data.doc_type}
							</MetaItem>
							<MetaItem label="Duration">
								{fmtDuration(data.execution_time_ms)}
							</MetaItem>
							<MetaItem label="File size">{fmtBytes(data.file_size)}</MetaItem>
							<MetaItem label="By">{data.user ?? "—"}</MetaItem>
							<MetaItem label="Agent">{data.agent ?? "—"}</MetaItem>
							<MetaItem label="Started">{fmtDate(data.started_at)}</MetaItem>
							<MetaItem label="Completed">
								{fmtDate(data.completed_at)}
							</MetaItem>
						</div>
					</div>

					{(data.source_databases.length > 0 ||
						data.source_docs.length > 0) && (
						<div className="card" style={{ marginBottom: "var(--md)" }}>
							{data.source_databases.length > 0 && (
								<div
									style={{
										marginBottom: data.source_docs.length > 0 ? "var(--md)" : 0,
									}}
								>
									<h3 style={{ margin: "0 0 var(--sm)" }}>Source databases</h3>
									<Chips items={data.source_databases} />
								</div>
							)}
							{data.source_docs.length > 0 && (
								<div>
									<h3 style={{ margin: "0 0 var(--sm)" }}>
										Source documentation
									</h3>
									<Chips items={data.source_docs} />
								</div>
							)}
						</div>
					)}

					{data.errors.length > 0 && (
						<div className="card" style={{ marginBottom: "var(--md)" }}>
							<h3 style={{ margin: "0 0 var(--sm)" }}>Errors</h3>
							<ul
								style={{
									margin: 0,
									paddingLeft: "var(--lg)",
									fontSize: "var(--text-sm)",
								}}
							>
								{data.errors.map((e) => (
									<li key={`${e.database ?? ""}|${e.error ?? ""}`}>
										{e.database && <strong>{e.database}</strong>}
										{e.database && e.error ? " — " : ""}
										{e.error}
									</li>
								))}
							</ul>
						</div>
					)}

					{data.error_message && (
						<div className="card" style={{ marginBottom: "var(--md)" }}>
							<h3 style={{ margin: "0 0 var(--sm)" }}>Error</h3>
							<pre style={{ ...PRE, color: "var(--error, #c0392b)" }}>
								{data.error_message}
							</pre>
						</div>
					)}

					{data.prompt_used && (
						<div className="card" style={{ marginBottom: "var(--md)" }}>
							<h3 style={{ margin: "0 0 var(--sm)" }}>Prompt used</h3>
							<pre style={PRE}>{data.prompt_used}</pre>
						</div>
					)}

					{data.agent_output && (
						<div className="card">
							<h3 style={{ margin: "0 0 var(--sm)" }}>Agent output</h3>
							<pre style={PRE}>{data.agent_output}</pre>
						</div>
					)}
				</>
			)}
		</div>
	);
}
