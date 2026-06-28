import { useMemo, useState } from "react";
import { apiErrorDetail } from "../api/client";
import {
	type ExecutionResult,
	executionDownloadUrl,
	type ReportMeta,
	sendExecutionEmail,
} from "../api/reports";

function StatusBadge({ status }: { status: ExecutionResult["status"] }) {
	if (status === "success")
		return <span className="badge badge-success">SUCCESS</span>;
	if (status === "failed")
		return <span className="badge badge-error">FAILED</span>;
	return <span className="badge badge-muted">RUNNING</span>;
}

function EmailButton({ executionId }: { executionId: string }) {
	const [state, setState] = useState<"idle" | "sending" | "sent">("idle");

	async function send() {
		if (state !== "idle") return;
		setState("sending");
		try {
			await sendExecutionEmail(executionId);
			setState("sent");
			window.setTimeout(() => setState("idle"), 3000);
		} catch (err) {
			window.alert(apiErrorDetail(err, "Failed to send email."));
			setState("idle");
		}
	}

	return (
		<button
			type="button"
			className="btn btn-ghost btn-sm"
			onClick={() => void send()}
			disabled={state === "sending"}
		>
			{state === "sending" ? (
				<i className="fa-solid fa-spinner fa-spin" />
			) : state === "sent" ? (
				<>
					<i className="fa-solid fa-check" /> Sent
				</>
			) : (
				<>
					<i className="fa-solid fa-envelope" /> Email
				</>
			)}
		</button>
	);
}

// Renders an execution's metadata header, the optional download / email / history
// controls, and a capped table preview. Shared by the workspace viewer and the
// admin run/preview/monitor views.
export function ReportResultTable({
	report,
	execution,
	emailEnabled = false,
	isPreview = false,
	onShowHistory,
}: {
	report: ReportMeta;
	execution: ExecutionResult;
	emailEnabled?: boolean;
	isPreview?: boolean;
	onShowHistory?: () => void;
}) {
	const hasData =
		execution.column_names.length > 0 && execution.rows.length > 0;
	const total = execution.row_count ?? execution.rows.length;
	const truncated = total > execution.rows.length;
	// Result-set rows have no natural id; their identity is their ordinal
	// position (the set is immutable and never reordered), so pair each with a
	// stable index-based id to use as the React key.
	const rows = useMemo(
		() => execution.rows.map((cells, idx) => ({ id: idx, cells })),
		[execution.rows],
	);

	return (
		<>
			<div className="report-meta">
				<div className="report-title-row">
					<h2 className="docs-title">{report.name}</h2>
					{hasData && (
						<div className="report-download-btns">
							<a
								className="btn btn-ghost btn-sm"
								href={executionDownloadUrl(execution.id, "csv")}
								title="Download CSV"
							>
								<i className="fa-solid fa-file-csv" /> CSV
							</a>
							<a
								className="btn btn-ghost btn-sm"
								href={executionDownloadUrl(execution.id, "excel")}
								title="Download Excel"
							>
								<i className="fa-solid fa-file-excel" /> Excel
							</a>
							{emailEnabled ? (
								<EmailButton executionId={execution.id} />
							) : (
								<button
									type="button"
									className="btn btn-ghost btn-sm"
									disabled
									title="Email not available — contact your administrator to configure SMTP"
								>
									<i className="fa-solid fa-envelope" /> Email
								</button>
							)}
						</div>
					)}
				</div>
				{report.description && <p className="text-sec">{report.description}</p>}
				<div className="report-info">
					<StatusBadge status={execution.status} />
					{execution.row_count != null && (
						<span className="badge badge-muted">
							{execution.row_count} rows
						</span>
					)}
					{execution.execution_time_ms != null && (
						<span className="badge badge-muted">
							{execution.execution_time_ms}ms
						</span>
					)}
					<span className="text-sec text-sm">
						{new Date(execution.started_at).toLocaleString()}
					</span>
					{isPreview && <span className="badge badge-orange">PREVIEW</span>}
					{onShowHistory && !isPreview && (
						<button
							type="button"
							className="btn btn-ghost btn-sm"
							onClick={onShowHistory}
						>
							<i className="fa-solid fa-clock-rotate-left" /> History
						</button>
					)}
				</div>
			</div>

			{execution.error_message && (
				<div style={{ marginTop: "var(--md)" }}>
					<pre
						style={{
							color: "var(--danger)",
							background: "var(--bg-warm)",
							padding: "var(--md)",
							borderRadius: "8px",
							overflowX: "auto",
						}}
					>
						{execution.error_message}
					</pre>
				</div>
			)}

			{hasData ? (
				<>
					{truncated && (
						<div className="report-preview-notice">
							<i className="fa-solid fa-circle-info" />
							Showing first {execution.rows.length} of {total} rows. Download
							the full report using the CSV or Excel buttons above.
						</div>
					)}
					<div className="report-table-wrap">
						<table className="report-table">
							<thead>
								<tr>
									{execution.column_names.map((col) => (
										<th key={col}>{col}</th>
									))}
								</tr>
							</thead>
							<tbody>
								{rows.map(({ id, cells }) => (
									<tr key={id}>
										{execution.column_names.map((col, j) => {
											const val = cells[j];
											return (
												<td key={col}>
													{val == null ? (
														<span className="text-muted">NULL</span>
													) : (
														String(val)
													)}
												</td>
											);
										})}
									</tr>
								))}
							</tbody>
						</table>
					</div>
				</>
			) : (
				execution.status === "success" && (
					<div className="docs-empty-state" style={{ marginTop: "var(--md)" }}>
						<p className="text-sec">Query returned no rows.</p>
					</div>
				)
			)}
		</>
	);
}
