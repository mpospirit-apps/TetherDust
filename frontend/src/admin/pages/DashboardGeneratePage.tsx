import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	getDashboardGenerateOptions,
	getDashboardGenStatus,
	startDashboardGenerate,
} from "../../api/dashboards";
import { FormField } from "../components/forms";
import {
	AgentSelect,
	SourceSelect,
	type SourceSelection,
} from "./DocGenShared";

const NO_SOURCES: SourceSelection = { databases: [], docs: [], codebases: [] };

function titleCase(value: string): string {
	return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function DashboardGeneratePage() {
	const options = useQuery({
		queryKey: ["admin", "dashboard-gen-options"],
		queryFn: getDashboardGenerateOptions,
	});

	const [name, setName] = useState("");
	const [dashboardType, setDashboardType] = useState("overview");
	const [promptOverride, setPromptOverride] = useState("");
	const [agent, setAgent] = useState("");
	const [sources, setSources] = useState<SourceSelection>(NO_SOURCES);
	const [error, setError] = useState<string | null>(null);
	const [logId, setLogId] = useState<string | null>(null);

	useEffect(() => {
		if (!agent && options.data) {
			const active = options.data.agents.find((a) => a.is_active);
			if (active) setAgent(active.id);
		}
	}, [options.data, agent]);

	const status = useQuery({
		queryKey: ["dashboard-gen-status", logId],
		queryFn: () => getDashboardGenStatus(logId as string),
		enabled: Boolean(logId),
		refetchInterval: (query) =>
			query.state.data?.status === "running" ? 2000 : false,
	});

	const start = useMutation({
		mutationFn: startDashboardGenerate,
		onSuccess: (res) => setLogId(res.log_id),
		onError: (err) =>
			setError(apiErrorDetail(err, "Could not start generation.")),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		start.mutate({
			dashboard_name: name,
			dashboard_type: dashboardType,
			prompt_override: promptOverride,
			agent,
			source_db: sources.databases,
			source_doc: sources.docs,
			source_codebase: sources.codebases,
		});
	}

	const opts = options.data;
	const s = status.data;

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Generate Dashboard</h1>
					<p>
						The agent explores your data and builds a dashboard of D3 charts
					</p>
				</div>
				<Link to="/admin/dashboards" className="btn btn-ghost">
					Back
				</Link>
			</div>

			{logId ? (
				<div className="card">
					{!s ? (
						<p className="text-sec">Starting…</p>
					) : s.status === "running" ? (
						<div className="doc-loading-state">
							<i className="fa-solid fa-spinner fa-spin" />
							<p>
								Building dashboard…{" "}
								{s.charts_created ? `${s.charts_created} charts so far` : ""}
							</p>
							{s.agent_output && (
								<p className="doc-loading-elapsed">
									{s.agent_output.slice(0, 200)}
								</p>
							)}
						</div>
					) : s.status === "failed" ? (
						<div className="flash flash-error">
							Generation failed: {s.error || "unknown error"}
						</div>
					) : (
						<div>
							<div className="flash flash-success">
								Created {s.charts_created ?? 0} chart(s) in “{s.dashboard_name}
								”.
							</div>
							<div className="form-actions" style={{ marginTop: "var(--md)" }}>
								{s.dashboard_id && (
									<Link
										to={`/dashboards/${s.dashboard_id}`}
										className="btn btn-primary"
									>
										View dashboard
									</Link>
								)}
								<Link to="/admin/dashboards" className="btn btn-secondary">
									Done
								</Link>
							</div>
						</div>
					)}
				</div>
			) : (
				<form onSubmit={onSubmit} className="card" style={{ maxWidth: 760 }}>
					{error && (
						<div
							className="flash flash-error"
							style={{ marginBottom: "var(--md)" }}
						>
							{error}
						</div>
					)}

					<div
						className="doc-req-row"
						style={{ gridTemplateColumns: "2fr 1fr" }}
					>
						<FormField label="Dashboard name" help="Must be unique.">
							<input
								className="form-control"
								value={name}
								required
								placeholder="Sales Overview"
								onChange={(e) => setName(e.target.value)}
							/>
						</FormField>
						<FormField label="Style">
							<select
								className="form-control"
								value={dashboardType}
								onChange={(e) => setDashboardType(e.target.value)}
							>
								{(opts?.dashboard_types ?? ["overview"]).map((t) => (
									<option key={t} value={t}>
										{titleCase(t)}
									</option>
								))}
							</select>
						</FormField>
					</div>

					<div className="doc-section">
						<div className="doc-section__title">Source material</div>
						{opts ? (
							<SourceSelect
								options={opts}
								value={sources}
								onChange={setSources}
							/>
						) : (
							<p className="text-sec">Loading…</p>
						)}
					</div>

					<FormField
						label="Custom instructions"
						help="Optional — replaces the default prompt for the chosen style."
					>
						<textarea
							className="form-control"
							rows={3}
							value={promptOverride}
							onChange={(e) => setPromptOverride(e.target.value)}
						/>
					</FormField>

					<FormField label="Agent" help="Generation runs on the active agent.">
						{opts ? (
							<AgentSelect options={opts} value={agent} onChange={setAgent} />
						) : (
							<p className="text-sec">Loading…</p>
						)}
					</FormField>

					<div className="form-actions">
						<button
							type="submit"
							className="btn btn-primary"
							disabled={start.isPending}
						>
							{start.isPending ? "Starting…" : "Generate Dashboard"}
						</button>
						<Link to="/admin/dashboards" className="btn btn-secondary">
							Cancel
						</Link>
					</div>
				</form>
			)}
		</div>
	);
}
