import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
	getExecution,
	getReportHistory,
	getReportLatest,
	getReports,
	type ReportListItem,
} from "../api/reports";
import { ReportResultTable } from "./ReportResultTable";

const GROUP_COLORS = [
	"var(--c-cyan)",
	"var(--c-lime)",
	"var(--c-pink)",
	"var(--c-orange)",
	"var(--c-red)",
];

const WEEKDAYS = [
	"Sunday",
	"Monday",
	"Tuesday",
	"Wednesday",
	"Thursday",
	"Friday",
	"Saturday",
];

function startOfDay(d: Date): Date {
	return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

// Mirrors the legacy `_report_group` bucketing (Today / Yesterday / weekday /
// "Month Year" / Never Run).
function groupLabel(iso: string | null): string {
	if (!iso) return "Never Run";
	const dt = new Date(iso);
	const todayStart = startOfDay(new Date());
	const yesterdayStart = new Date(todayStart.getTime() - 86_400_000);
	if (dt >= todayStart) return "Today";
	if (dt >= yesterdayStart) return "Yesterday";
	const dayStart = startOfDay(dt);
	const daysAgo = Math.round(
		(todayStart.getTime() - dayStart.getTime()) / 86_400_000,
	);
	if (daysAgo <= 7) return WEEKDAYS[dt.getDay()];
	return dt.toLocaleString(undefined, { month: "long", year: "numeric" });
}

function groupSortKey(label: string): [number, number] {
	if (label === "Today") return [0, 0];
	if (label === "Yesterday") return [1, 0];
	if (label === "Never Run") return [999, 0];
	const wd = WEEKDAYS.indexOf(label);
	if (wd >= 0) return [2, wd];
	const parsed = new Date(`${label} 1`);
	if (!Number.isNaN(parsed.getTime()))
		return [3, -(parsed.getFullYear() * 12 + parsed.getMonth())];
	return [4, 0];
}

interface Group {
	label: string;
	reports: ReportListItem[];
}

function buildGroups(reports: ReportListItem[]): Group[] {
	const map = new Map<string, ReportListItem[]>();
	for (const r of reports) {
		const label = groupLabel(r.latest_run?.started_at ?? null);
		const bucket = map.get(label);
		if (bucket) bucket.push(r);
		else map.set(label, [r]);
	}
	return [...map.entries()]
		.sort((a, b) => {
			const ka = groupSortKey(a[0]);
			const kb = groupSortKey(b[0]);
			return ka[0] - kb[0] || ka[1] - kb[1];
		})
		.map(([label, items]) => ({ label, reports: items }));
}

type Content =
	| { kind: "latest" }
	| { kind: "history" }
	| { kind: "execution"; execId: string };

function LatestView({
	reportId,
	onShowHistory,
}: {
	reportId: string;
	onShowHistory: () => void;
}) {
	const { data, isLoading, isError } = useQuery({
		queryKey: ["report-latest", reportId],
		queryFn: () => getReportLatest(reportId),
	});
	if (isLoading) return <Loading />;
	if (isError || !data)
		return <p className="text-sec">Failed to load report.</p>;
	if (!data.execution) {
		return (
			<div className="docs-empty-state">
				<p>No results yet. This report has not been run.</p>
			</div>
		);
	}
	return (
		<div className="card">
			<ReportResultTable
				report={data.report}
				execution={data.execution}
				emailEnabled={data.email_enabled}
				onShowHistory={onShowHistory}
			/>
		</div>
	);
}

function HistoryView({
	reportId,
	onOpenExecution,
}: {
	reportId: string;
	onOpenExecution: (execId: string) => void;
}) {
	const { data, isLoading, isError } = useQuery({
		queryKey: ["report-history", reportId],
		queryFn: () => getReportHistory(reportId),
	});
	if (isLoading) return <Loading />;
	if (isError || !data)
		return <p className="text-sec">Failed to load history.</p>;
	return (
		<div>
			<h3 style={{ marginBottom: "var(--md)" }}>History: {data.report.name}</h3>
			{data.executions.length === 0 ? (
				<p className="text-sec">No executions yet.</p>
			) : (
				<div className="card">
					<div className="report-table-wrap">
						<table className="report-table">
							<thead>
								<tr>
									<th>Status</th>
									<th>Started</th>
									<th>Duration</th>
									<th>Rows</th>
									<th />
								</tr>
							</thead>
							<tbody>
								{data.executions.map((ex) => (
									<tr key={ex.id}>
										<td>
											<span
												className={
													ex.status === "success"
														? "badge badge-success"
														: ex.status === "failed"
															? "badge badge-error"
															: "badge badge-muted"
												}
											>
												{ex.status.toUpperCase()}
											</span>
										</td>
										<td>{new Date(ex.started_at).toLocaleString()}</td>
										<td>
											{ex.execution_time_ms != null
												? `${ex.execution_time_ms}ms`
												: "—"}
										</td>
										<td>{ex.row_count ?? "—"}</td>
										<td>
											<button
												type="button"
												className="btn btn-ghost btn-sm"
												onClick={() => onOpenExecution(ex.id)}
											>
												<i className="fa-solid fa-eye" /> View
											</button>
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				</div>
			)}
		</div>
	);
}

function ExecutionView({ execId }: { execId: string }) {
	const { data, isLoading, isError } = useQuery({
		queryKey: ["execution", execId],
		queryFn: () => getExecution(execId),
	});
	if (isLoading) return <Loading />;
	if (isError || !data)
		return <p className="text-sec">Failed to load execution.</p>;
	return (
		<div className="card">
			<ReportResultTable
				report={data.report}
				execution={data.execution}
				emailEnabled={data.email_enabled}
			/>
		</div>
	);
}

function Loading() {
	return (
		<div className="docs-loading">
			<i className="fa-solid fa-spinner fa-spin" />
		</div>
	);
}

export function ReportsPage() {
	const { data, isLoading } = useQuery({
		queryKey: ["reports"],
		queryFn: getReports,
	});
	const [selectedId, setSelectedId] = useState<string | null>(null);
	const [content, setContent] = useState<Content>({ kind: "latest" });

	const groups = useMemo(() => buildGroups(data?.reports ?? []), [data]);

	function selectReport(id: string) {
		setSelectedId(id);
		setContent({ kind: "latest" });
	}

	const hasReports = (data?.reports.length ?? 0) > 0;

	return (
		<div className="docs-layout">
			<aside className="docs-sidebar">
				<div className="docs-tree">
					{isLoading ? (
						<p className="text-sec" style={{ padding: "var(--md) var(--lg)" }}>
							Loading…
						</p>
					) : !hasReports ? (
						<p className="text-sec" style={{ padding: "var(--md) var(--lg)" }}>
							No reports available.
						</p>
					) : (
						groups.map((group, idx) => (
							<div key={group.label}>
								<div
									className="history-section-label"
									style={{ color: GROUP_COLORS[idx % GROUP_COLORS.length] }}
								>
									{group.label}
								</div>
								{group.reports.map((r) => (
									<button
										key={r.id}
										type="button"
										className={
											selectedId === r.id
												? "docs-file-btn report-sidebar-item active"
												: "docs-file-btn report-sidebar-item"
										}
										onClick={() => selectReport(r.id)}
									>
										<i className="fa-solid fa-table-list" />
										<span>{r.name}</span>
									</button>
								))}
							</div>
						))
					)}
				</div>
			</aside>

			<div className="docs-content-area">
				<div className="docs-content">
					{!selectedId ? (
						<div className="docs-empty-state">
							<p>
								Select a report from the sidebar to view its latest results.
							</p>
						</div>
					) : content.kind === "history" ? (
						<HistoryView
							reportId={selectedId}
							onOpenExecution={(execId) =>
								setContent({ kind: "execution", execId })
							}
						/>
					) : content.kind === "execution" ? (
						<ExecutionView execId={content.execId} />
					) : (
						<LatestView
							reportId={selectedId}
							onShowHistory={() => setContent({ kind: "history" })}
						/>
					)}
				</div>
			</div>
		</div>
	);
}
