import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
	getAdminOverview,
	type OverviewDelta,
	type TrendDay,
} from "../../api/admin";

const SPARK_W = 100;
const SPARK_H = 30;
const SPARK_PAD = 3;

/** SVG polyline `points` string for a small inline sparkline. */
function sparklinePoints(values: number[]): string {
	if (values.length === 0) return "";
	const mx = Math.max(...values) || 1;
	const n = values.length;
	const span = SPARK_H - 2 * SPARK_PAD;
	const step = n > 1 ? SPARK_W / (n - 1) : 0;
	return values
		.map((v, i) => {
			const x = Math.round(i * step * 100) / 100;
			const y = Math.round((SPARK_H - SPARK_PAD - (v / mx) * span) * 100) / 100;
			return `${x},${y}`;
		})
		.join(" ");
}

/** Day-of-month from a "YYYY-MM-DD" string (tz-safe). */
function dayNum(iso: string): number {
	return Number(iso.slice(8, 10));
}

function shortDate(iso: string): string {
	const [y, m, d] = iso.split("-").map(Number);
	return new Date(y, m - 1, d).toLocaleDateString(undefined, {
		month: "short",
		day: "numeric",
	});
}

function shortTime(iso: string): string {
	return new Date(iso).toLocaleString(undefined, {
		month: "short",
		day: "numeric",
		hour: "2-digit",
		minute: "2-digit",
	});
}

function TrendBadge({
	delta,
	inverse = false,
}: {
	delta: OverviewDelta;
	inverse?: boolean;
}) {
	const icon =
		delta.dir === "up"
			? "fa-arrow-up"
			: delta.dir === "down"
				? "fa-arrow-down"
				: "fa-minus";
	return (
		<span
			className={`mc-trend mc-trend--${delta.dir}${inverse ? " mc-trend--inverse" : ""}`}
		>
			<i className={`fa-solid ${icon}`} />
			{delta.pct !== null ? `${delta.pct}%` : "—"}
		</span>
	);
}

function TrendBars({ trend }: { trend: TrendDay[] }) {
	const maxTotal = Math.max(...trend.map((d) => d.total), 0) || 1;
	return (
		<div className="mc-bars">
			{trend.map((d) => (
				<div
					key={d.date}
					className="mc-bars__col"
					title={`${shortDate(d.date)} — ${d.total} quer${
						d.total === 1 ? "y" : "ies"
					}, ${d.failed} failed`}
				>
					<div className="mc-bars__track">
						<div
							className="mc-bars__seg mc-bars__seg--fail"
							style={{ height: `${(d.failed / maxTotal) * 100}%` }}
						/>
						<div
							className="mc-bars__seg mc-bars__seg--ok"
							style={{ height: `${(d.ok / maxTotal) * 100}%` }}
						/>
					</div>
					<div className="mc-bars__label">{dayNum(d.date)}</div>
				</div>
			))}
		</div>
	);
}

export function AdminHome() {
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "overview"],
		queryFn: getAdminOverview,
	});

	if (isLoading) {
		return (
			<div>
				<div className="page-header">
					<div>
						<h1>Mission Control</h1>
						<p>System overview, activity, and health</p>
					</div>
				</div>
				<div className="card">
					<p className="text-sec">Loading…</p>
				</div>
			</div>
		);
	}

	if (isError || !data) {
		return (
			<div>
				<div className="page-header">
					<div>
						<h1>Mission Control</h1>
						<p>System overview, activity, and health</p>
					</div>
				</div>
				<div className="card">
					<p className="text-sec">Failed to load overview.</p>
				</div>
			</div>
		);
	}

	const { metrics, kpis, trend, top_databases, health, recent_queries } = data;
	const recentSessions = data.recent_sessions;
	const maxDb = top_databases[0]?.count ?? 1;

	return (
		<div>
			<div className="page-header mc-header">
				<div>
					<h1>Mission Control</h1>
					<p>System overview, activity, and health</p>
				</div>
				<div className="mc-asof">As of {shortTime(data.generated_at)}</div>
			</div>

			{/* Health banner */}
			<div className={`mc-health mc-health--${health.status}`}>
				<div className="mc-health__status">
					<span className="mc-health__dot" />
					<div>
						<div className="mc-health__label">{health.label}</div>
						<div className="mc-health__detail">{health.detail}</div>
					</div>
				</div>
				<div className="mc-health__meta">
					{health.agent ? (
						<div className="mc-health__item">
							<span className="mc-health__item-label">Active agent</span>
							<span className="mc-health__item-value">
								<i className="fa-solid fa-robot" /> {health.agent.name}{" "}
								<span className="text-muted">· {health.agent.type}</span>
							</span>
						</div>
					) : (
						<Link to="/admin/agents/new" className="btn btn-primary btn-sm">
							Configure an agent
						</Link>
					)}
				</div>
			</div>

			{/* Inventory chips */}
			<div className="mc-chips">
				<Link to="/admin/databases" className="mc-chip">
					<i className="fa-solid fa-database" />
					<span className="mc-chip__value">
						{metrics.active_databases}
						<span className="mc-chip__sub">/{metrics.total_databases}</span>
					</span>
					<span className="mc-chip__label">Databases</span>
				</Link>
				<Link to="/admin/mcp-servers" className="mc-chip">
					<i className="fa-solid fa-wrench" />
					<span className="mc-chip__value">
						{metrics.active_tools}
						<span className="mc-chip__sub">/{metrics.total_tools}</span>
					</span>
					<span className="mc-chip__label">Tools</span>
				</Link>
				<Link to="/admin/docsources" className="mc-chip">
					<i className="fa-solid fa-book" />
					<span className="mc-chip__value">{metrics.doc_sources}</span>
					<span className="mc-chip__label">Documentations</span>
				</Link>
				<Link to="/admin/tethers" className="mc-chip">
					<i className="fa-solid fa-link" />
					<span className="mc-chip__value">{metrics.tethers}</span>
					<span className="mc-chip__label">Tethers</span>
				</Link>
				<Link to="/admin/users" className="mc-chip">
					<i className="fa-solid fa-users" />
					<span className="mc-chip__value">{metrics.total_users}</span>
					<span className="mc-chip__label">Users</span>
				</Link>
				<Link to="/admin/roles" className="mc-chip">
					<i className="fa-solid fa-shield-halved" />
					<span className="mc-chip__value">{metrics.total_roles}</span>
					<span className="mc-chip__label">Roles</span>
				</Link>
			</div>

			{/* Hero KPIs */}
			<div className="mc-kpis">
				<div className="mc-kpi">
					<div className="mc-kpi__top">
						<span className="mc-kpi__label">Queries · 24h</span>
						<TrendBadge delta={kpis.queries.delta} />
					</div>
					<div className="mc-kpi__value">{metrics.queries_24h}</div>
					<svg
						className="mc-spark"
						viewBox="0 0 100 30"
						preserveAspectRatio="none"
						aria-hidden="true"
					>
						<polyline
							points={sparklinePoints(trend.map((d) => d.total))}
							fill="none"
							stroke="var(--c-cyan)"
							strokeWidth="1.5"
							vectorEffect="non-scaling-stroke"
						/>
					</svg>
					<div className="mc-kpi__foot">vs previous 24h</div>
				</div>

				<div className="mc-kpi">
					<div className="mc-kpi__top">
						<span className="mc-kpi__label">Success rate · 24h</span>
					</div>
					<div className="mc-kpi__value">
						{metrics.success_rate}
						<span className="mc-kpi__unit">%</span>
					</div>
					<div className="mc-meter">
						<div
							className="mc-meter__fill"
							style={{ width: `${metrics.success_rate}%` }}
						/>
					</div>
					<div className="mc-kpi__foot">
						{metrics.queries_24h} quer{metrics.queries_24h === 1 ? "y" : "ies"}{" "}
						ran
					</div>
				</div>

				<div className="mc-kpi">
					<div className="mc-kpi__top">
						<span className="mc-kpi__label">Active sessions · 24h</span>
						<TrendBadge delta={kpis.sessions.delta} />
					</div>
					<div className="mc-kpi__value">{metrics.active_sessions}</div>
					<div className="mc-kpi__foot">chat sessions active</div>
				</div>

				<div className="mc-kpi">
					<div className="mc-kpi__top">
						<span className="mc-kpi__label">Failed queries · 24h</span>
						<TrendBadge delta={kpis.failed.delta} inverse />
					</div>
					<div className="mc-kpi__value">{metrics.failed_queries_24h}</div>
					<div className="mc-kpi__foot">
						{metrics.failed_queries_24h ? (
							<Link to="/admin/audit">investigate →</Link>
						) : (
							"no failures"
						)}
					</div>
				</div>
			</div>

			{/* Trends row */}
			<div className="mc-trends">
				<div className="card mc-chart-card">
					<div className="card-header">
						<h2>Query volume · {trend.length} days</h2>
						<div className="mc-legend">
							<span className="mc-legend__item">
								<span className="mc-legend__swatch mc-legend__swatch--ok" />{" "}
								Success
							</span>
							<span className="mc-legend__item">
								<span className="mc-legend__swatch mc-legend__swatch--fail" />{" "}
								Failed
							</span>
						</div>
					</div>
					<TrendBars trend={trend} />
				</div>

				<div className="card mc-chart-card">
					<div className="card-header">
						<h2>Top databases · 7 days</h2>
					</div>
					{top_databases.length > 0 ? (
						<div className="mc-topdb">
							{top_databases.map((row) => (
								<div key={row.name} className="mc-topdb__row">
									<div className="mc-topdb__name">{row.name}</div>
									<div className="mc-topdb__bar">
										<div
											className="mc-topdb__fill"
											style={{ width: `${(row.count / maxDb) * 100}%` }}
										/>
									</div>
									<div className="mc-topdb__count">{row.count}</div>
								</div>
							))}
						</div>
					) : (
						<div className="empty-state empty-state--sm">
							<div className="icon">
								<i className="fa-solid fa-database" />
							</div>
							<p className="text-sec">No queries in the last 7 days.</p>
						</div>
					)}
				</div>
			</div>

			{/* Activity feeds */}
			<div className="mc-feeds">
				<div className="card">
					<div className="card-header">
						<h2>Recent Queries</h2>
						<Link to="/admin/audit" className="btn btn-ghost btn-sm">
							View All
						</Link>
					</div>
					{recent_queries.length > 0 ? (
						<div className="table-wrap">
							<table>
								<thead>
									<tr>
										<th>User</th>
										<th>Database</th>
										<th>Status</th>
										<th>Rows</th>
										<th>ms</th>
										<th>When</th>
									</tr>
								</thead>
								<tbody>
									{recent_queries.map((log) => (
										<tr key={log.id}>
											<td>{log.user ?? "—"}</td>
											<td>{log.database ?? "—"}</td>
											<td>
												{log.success ? (
													<span className="badge badge-success">OK</span>
												) : (
													<span className="badge badge-error">FAIL</span>
												)}
											</td>
											<td>{log.row_count ?? "—"}</td>
											<td>{log.execution_time_ms ?? "—"}</td>
											<td className="text-sec text-sm">
												{shortTime(log.created_at)}
											</td>
										</tr>
									))}
								</tbody>
							</table>
						</div>
					) : (
						<div className="empty-state">
							<div className="icon">
								<i className="fa-solid fa-list-check" />
							</div>
							<h3>No Queries Yet</h3>
							<p className="text-sec">Query audit logs will appear here.</p>
						</div>
					)}
				</div>

				<div className="card">
					<div className="card-header">
						<h2>Recent Chat Sessions</h2>
						<Link to="/admin/sessions" className="btn btn-ghost btn-sm">
							View All
						</Link>
					</div>
					{recentSessions.length > 0 ? (
						<div className="table-wrap">
							<table>
								<thead>
									<tr>
										<th>Session</th>
										<th>User</th>
										<th>Msgs</th>
										<th>Last Activity</th>
									</tr>
								</thead>
								<tbody>
									{recentSessions.map((s) => (
										<tr key={s.id}>
											<td className="truncate">{s.title || "Untitled"}</td>
											<td>{s.user ?? "—"}</td>
											<td>{s.message_count}</td>
											<td className="text-sec text-sm">
												{shortTime(s.updated_at)}
											</td>
										</tr>
									))}
								</tbody>
							</table>
						</div>
					) : (
						<div className="empty-state">
							<div className="icon">
								<i className="fa-solid fa-comments" />
							</div>
							<h3>No Sessions Yet</h3>
							<p className="text-sec">Chat sessions will appear here.</p>
						</div>
					)}
				</div>
			</div>
		</div>
	);
}
