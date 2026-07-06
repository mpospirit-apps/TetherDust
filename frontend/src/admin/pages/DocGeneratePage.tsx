import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import { getGenerateOptions, startGenerate } from "../../api/docs";
import { FormField } from "../components/forms";
import {
	AgentSelect,
	SourceSelect,
	type SourceSelection,
	StatusPanel,
	useDocGenStatus,
} from "./DocGenShared";

const NO_SOURCES: SourceSelection = { databases: [], docs: [], codebases: [] };

export function DocGeneratePage() {
	const options = useQuery({
		queryKey: ["admin", "docsource-options"],
		queryFn: getGenerateOptions,
	});

	const [docName, setDocName] = useState("");
	const [docType, setDocType] = useState("database");
	const [destination, setDestination] = useState("");
	const [scope, setScope] = useState("");
	const [agent, setAgent] = useState("");
	const [sources, setSources] = useState<SourceSelection>(NO_SOURCES);
	const [error, setError] = useState<string | null>(null);
	const [logId, setLogId] = useState<string | null>(null);
	const [howItWorksOpen, setHowItWorksOpen] = useState(false);

	// Default the agent to the active one once options load.
	useEffect(() => {
		if (!agent && options.data) {
			const active = options.data.agents.find((a) => a.is_active);
			if (active) setAgent(active.id);
		}
	}, [options.data, agent]);

	const status = useDocGenStatus(logId);

	const start = useMutation({
		mutationFn: startGenerate,
		onSuccess: (res) => setLogId(res.log_id),
		onError: (err) =>
			setError(apiErrorDetail(err, "Could not start generation.")),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		start.mutate({
			doc_name: docName,
			doc_type: docType,
			destination,
			scope,
			agent,
			source_db: sources.databases,
			source_doc: sources.docs,
			source_codebase: sources.codebases,
		});
	}

	function reset() {
		setLogId(null);
		setDocName("");
		setScope("");
	}

	const opts = options.data;

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Generate Documentation</h1>
					<p>
						The agent writes a single page and saves it via the
						create_documentation tool
					</p>
				</div>
				{!logId && (
					<div className="form-actions">
						<Link to="/admin/docsources" className="btn btn-ghost">
							Cancel
						</Link>
						<button
							type="submit"
							form="doc-generate-form"
							className="btn btn-primary"
							disabled={start.isPending}
						>
							{start.isPending ? "Starting…" : "Generate"}
						</button>
					</div>
				)}
			</div>

			{logId ? (
				<div className="card">
					{status.data ? (
						<StatusPanel status={status.data} />
					) : (
						<p className="text-sec">Starting…</p>
					)}
					{status.data && status.data.status !== "running" && (
						<div className="form-actions" style={{ marginTop: "var(--md)" }}>
							<Link to="/admin/docsources" className="btn btn-primary">
								Done
							</Link>
							<button
								type="button"
								className="btn btn-secondary"
								onClick={reset}
							>
								Generate another
							</button>
						</div>
					)}
				</div>
			) : (
				<form id="doc-generate-form" onSubmit={onSubmit}>
					{error && (
						<div
							className="flash flash-error"
							style={{ marginBottom: "var(--md)" }}
						>
							{error}
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
											Pick a template, optional scope, and select your data
											sources
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
											<i className="fa-solid fa-pen-to-square" />
										</div>
										<div className="doc-hiw-label">Agent writes</div>
										<div className="doc-hiw-desc">
											Calls create_documentation once with the full markdown
										</div>
									</div>
									<div className="doc-hiw-arrow">
										<i className="fa-solid fa-chevron-right" />
									</div>
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-file-lines" />
										</div>
										<div className="doc-hiw-label">One page saved</div>
										<div className="doc-hiw-desc">
											A single .md file in your chosen destination folder
										</div>
									</div>
								</div>
							</div>
						</div>
					</div>

					<div className="form-split">
						<div className="card">
							<h3 style={{ margin: "0 0 var(--md)" }}>Page details</h3>
							<div
								className="doc-req-row"
								style={{ gridTemplateColumns: "1fr 1fr" }}
							>
								<FormField label="File name" help="Saved as <name>.md.">
									<input
										className="form-control"
										value={docName}
										required
										placeholder="Orders"
										onChange={(e) => setDocName(e.target.value)}
									/>
								</FormField>
								<FormField label="Type">
									<select
										className="form-control"
										value={docType}
										onChange={(e) => setDocType(e.target.value)}
									>
										{(opts?.doc_types ?? []).map((t) => (
											<option key={t.value} value={t.value}>
												{t.label}
											</option>
										))}
									</select>
								</FormField>
							</div>

							<FormField
								label="Destination folder"
								help="Existing or new folder under documentations/."
							>
								<input
									className="form-control"
									list="dest-folders"
									value={destination}
									required
									placeholder="MyDatabase"
									onChange={(e) => setDestination(e.target.value)}
								/>
								<datalist id="dest-folders">
									{(opts?.dest_folders ?? []).map((f) => (
										<option key={f} value={f} />
									))}
								</datalist>
							</FormField>

							<FormField
								label="Scope & goals"
								help="Optional — steer what the page should cover."
							>
								<textarea
									className="form-control"
									rows={3}
									value={scope}
									onChange={(e) => setScope(e.target.value)}
								/>
							</FormField>
						</div>

						<div className="card">
							<h3 style={{ margin: "0 0 var(--md)" }}>Source & agent</h3>
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
								label="Agent"
								help="Generation runs on the active agent."
							>
								{opts ? (
									<AgentSelect
										options={opts}
										value={agent}
										onChange={setAgent}
									/>
								) : (
									<p className="text-sec">Loading…</p>
								)}
							</FormField>
						</div>
					</div>
				</form>
			)}
		</div>
	);
}
