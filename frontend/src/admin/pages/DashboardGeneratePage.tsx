import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import Markdown from "react-markdown";
import { Link } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { getAgentStatus } from "../../api/chat";
import { apiErrorDetail } from "../../api/client";
import {
	getDashboardGenerateOptions,
	getDashboardGenStatus,
	previewDashboardGenerate,
	startDashboardGenerate,
} from "../../api/dashboards";
import { CustomSelect, FormField } from "../components/forms";
import { WizardSectionHeading, type WizardStepDef } from "../components/wizard";
import { SourceSelect, type SourceSelection } from "./DocGenShared";

const NO_SOURCES: SourceSelection = { databases: [], docs: [], codebases: [] };

// Identity first, the required generation config next, then the prompt preview.
const STEPS: WizardStepDef[] = [
	{
		key: "identity",
		label: "Identity",
		description: "Name the dashboard.",
	},
	{
		key: "configuration",
		label: "Configuration",
		description:
			"Write instructions and pick source material to generate from.",
	},
	{
		key: "prompt",
		label: "Prompt",
		description: "Preview the exact prompt that will be sent to the agent.",
	},
];

function titleCase(value: string): string {
	return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function DashboardGeneratePage() {
	const options = useQuery({
		queryKey: ["admin", "dashboard-gen-options"],
		queryFn: getDashboardGenerateOptions,
	});

	const agentStatus = useQuery({
		queryKey: ["agent-status"],
		queryFn: getAgentStatus,
	});

	const [name, setName] = useState("");
	const [dashboardType, setDashboardType] = useState("custom");
	const [promptOverride, setPromptOverride] = useState("");
	const [sources, setSources] = useState<SourceSelection>(NO_SOURCES);
	const [error, setError] = useState<string | null>(null);
	const [logId, setLogId] = useState<string | null>(null);
	const [howItWorksOpen, setHowItWorksOpen] = useState(false);

	// Debounce the Prompt step's live preview so it doesn't refetch on every
	// keystroke — settles 400ms after the last change to any input it depends on.
	const [previewInputs, setPreviewInputs] = useState({
		dashboard_name: name,
		dashboard_type: dashboardType,
		prompt_override: promptOverride,
		source_db: sources.databases,
		source_doc: sources.docs,
		source_codebase: sources.codebases,
	});
	useEffect(() => {
		const timer = setTimeout(() => {
			setPreviewInputs({
				dashboard_name: name,
				dashboard_type: dashboardType,
				prompt_override: promptOverride,
				source_db: sources.databases,
				source_doc: sources.docs,
				source_codebase: sources.codebases,
			});
		}, 400);
		return () => clearTimeout(timer);
	}, [name, dashboardType, promptOverride, sources]);

	const preview = useQuery({
		queryKey: ["dashboard-gen-preview", previewInputs],
		queryFn: () => previewDashboardGenerate(previewInputs),
		placeholderData: keepPreviousData,
	});

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
			source_db: sources.databases,
			source_doc: sources.docs,
			source_codebase: sources.codebases,
		});
	}

	const opts = options.data;
	const s = status.data;
	const noActiveAgent = agentStatus.data ? !agentStatus.data.name : false;

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Generate Dashboard</h1>
					<p>
						The agent explores your data and builds a dashboard of D3 charts
					</p>
				</div>
				{!logId && (
					<div className="form-actions">
						<Link to="/admin/dashboards" className="btn btn-ghost">
							Cancel
						</Link>
						<button
							type="submit"
							form="dashboard-generate-form"
							className="btn btn-primary"
							disabled={start.isPending || noActiveAgent}
						>
							{start.isPending ? "Starting…" : "Generate Dashboard"}
						</button>
					</div>
				)}
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
				<form id="dashboard-generate-form" onSubmit={onSubmit}>
					{error && (
						<div
							className="flash flash-error"
							style={{ marginBottom: "var(--md)" }}
						>
							{error}
						</div>
					)}
					{noActiveAgent && (
						<div
							className="flash flash-error"
							style={{ marginBottom: "var(--md)" }}
						>
							No active agent configured. Set one active under Agents before
							generating.
						</div>
					)}

					<div className="card doc-hiw-card">
						<button
							type="button"
							className="doc-hiw-toggle"
							aria-expanded={howItWorksOpen}
							onClick={() => setHowItWorksOpen((open) => !open)}
						>
							<h3>How it works</h3>
							<i
								className={`fa-solid fa-chevron-down doc-hiw-chevron${
									howItWorksOpen ? " is-open" : ""
								}`}
							/>
						</button>
						<div
							className={`doc-hiw-collapse${howItWorksOpen ? " is-open" : ""}`}
						>
							<div className="doc-hiw-collapse__inner">
								<div className="doc-hiw">
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-sliders" />
										</div>
										<div className="doc-hiw-label">Configure</div>
										<div className="doc-hiw-desc">
											Name the dashboard, write instructions (or pick a preset),
											and select your data sources
										</div>
									</div>
									<div className="doc-hiw-arrow">
										<i className="fa-solid fa-chevron-right" />
									</div>
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-magnifying-glass" />
										</div>
										<div className="doc-hiw-label">Agent explores</div>
										<div className="doc-hiw-desc">
											Reads table schemas, query examples, and codebase files
										</div>
									</div>
									<div className="doc-hiw-arrow">
										<i className="fa-solid fa-chevron-right" />
									</div>
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-chart-simple" />
										</div>
										<div className="doc-hiw-label">Agent builds charts</div>
										<div className="doc-hiw-desc">
											Writes a SQL query and d3 code for each chart, one call
											per chart
										</div>
									</div>
									<div className="doc-hiw-arrow">
										<i className="fa-solid fa-chevron-right" />
									</div>
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-table-cells-large" />
										</div>
										<div className="doc-hiw-label">Dashboard saved</div>
										<div className="doc-hiw-desc">
											A new dashboard filled with ready-to-view charts
										</div>
									</div>
								</div>
							</div>
						</div>
					</div>

					<div className="form-split-col">
						<div className="form-split">
							<div className="wizard-section">
								<WizardSectionHeading step={STEPS[0]} index={0} />
								<div className="card">
									<FormField label="Dashboard name" help="Must be unique.">
										<input
											className="form-control"
											value={name}
											required
											placeholder="Sales Overview"
											onChange={(e) => setName(e.target.value)}
										/>
									</FormField>
								</div>
							</div>

							<div className="wizard-section">
								<WizardSectionHeading step={STEPS[1]} index={1} />
								<div className="card">
									<FormField
										label="Instructions"
										help={
											dashboardType === "custom"
												? "Write what you want generated."
												: undefined
										}
									>
										<CustomSelect
											value={dashboardType}
											onChange={setDashboardType}
											options={(opts?.dashboard_types ?? ["custom"]).map(
												(t) => ({ value: t, label: titleCase(t) }),
											)}
										/>
										{dashboardType === "custom" && (
											<textarea
												className="form-control"
												style={{ marginTop: "var(--sm)" }}
												rows={3}
												value={promptOverride}
												required
												onChange={(e) => setPromptOverride(e.target.value)}
											/>
										)}
									</FormField>

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
								</div>
							</div>
						</div>

						<div className="wizard-section">
							<WizardSectionHeading step={STEPS[2]} index={2} />
							<div className="card">
								<FormField
									label="Prompt"
									help="Read-only — updates automatically as the fields above change. Text in accent lime comes from the Configuration step."
								>
									<div className="doc-result-preview__content">
										{preview.isLoading ? (
											<Markdown remarkPlugins={[remarkGfm]}>
												_Loading preview…_
											</Markdown>
										) : preview.data?.segments.length ? (
											preview.data.segments.map((seg, i) => (
												<div
													// biome-ignore lint/suspicious/noArrayIndexKey: segments are a stable, ordered structure with no natural id
													key={i}
													className={
														seg.is_configuration
															? "prompt-preview__config"
															: undefined
													}
												>
													<Markdown remarkPlugins={[remarkGfm]}>
														{seg.text}
													</Markdown>
												</div>
											))
										) : (
											<Markdown remarkPlugins={[remarkGfm]}>_(empty)_</Markdown>
										)}
									</div>
								</FormField>
							</div>
						</div>
					</div>
				</form>
			)}
		</div>
	);
}
