import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import { getGenerateOptions, startGenerateLibrary } from "../../api/docs";
import { FormField } from "../components/forms";
import {
	AgentSelect,
	SourceSelect,
	type SourceSelection,
	StatusPanel,
	useDocGenStatus,
} from "./DocGenShared";

const NO_SOURCES: SourceSelection = { databases: [], docs: [], codebases: [] };

export function DocLibraryPage() {
	const options = useQuery({
		queryKey: ["admin", "docsource-options"],
		queryFn: getGenerateOptions,
	});

	const [libraryName, setLibraryName] = useState("");
	const [sourceDocType, setSourceDocType] = useState("database");
	const [agent, setAgent] = useState("");
	const [sources, setSources] = useState<SourceSelection>(NO_SOURCES);
	const [error, setError] = useState<string | null>(null);
	const [logId, setLogId] = useState<string | null>(null);
	const [howItWorksOpen, setHowItWorksOpen] = useState(false);

	useEffect(() => {
		if (!agent && options.data) {
			const active = options.data.agents.find((a) => a.is_active);
			if (active) setAgent(active.id);
		}
	}, [options.data, agent]);

	const status = useDocGenStatus(logId);

	const start = useMutation({
		mutationFn: startGenerateLibrary,
		onSuccess: (res) => setLogId(res.log_id),
		onError: (err) =>
			setError(apiErrorDetail(err, "Could not start generation.")),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		start.mutate({
			library_name: libraryName,
			source_doc_type: sourceDocType,
			agent,
			source_db: sources.databases,
			source_doc: sources.docs,
			source_codebase: sources.codebases,
		});
	}

	const opts = options.data;

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Generate Documentation Library</h1>
					<p>
						The agent plans a folder tree and writes many pages, one per
						subsystem or table
					</p>
				</div>
				{!logId && (
					<div className="form-actions">
						<Link to="/admin/docsources" className="btn btn-ghost">
							Cancel
						</Link>
						<button
							type="submit"
							form="doc-library-form"
							className="btn btn-primary"
							disabled={start.isPending}
						>
							{start.isPending ? "Starting…" : "Generate Library"}
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
								onClick={() => {
									setLogId(null);
									setLibraryName("");
								}}
							>
								Generate another
							</button>
						</div>
					)}
				</div>
			) : (
				<form id="doc-library-form" onSubmit={onSubmit}>
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
											Name the library and select your data sources
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
											Reads schemas, existing docs, and codebase files
										</div>
									</div>
									<div className="doc-hiw-arrow">
										<i className="fa-solid fa-chevron-right" />
									</div>
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-sitemap" />
										</div>
										<div className="doc-hiw-label">Agent plans</div>
										<div className="doc-hiw-desc">
											Designs a folder tree and page outline for the library
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
											Calls create_documentation per file — subfolders created
											automatically
										</div>
									</div>
									<div className="doc-hiw-arrow">
										<i className="fa-solid fa-chevron-right" />
									</div>
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-folder-tree" />
										</div>
										<div className="doc-hiw-label">Library saved</div>
										<div className="doc-hiw-desc">
											A cross-linked tree of .md files under one root folder
										</div>
									</div>
								</div>
							</div>
						</div>
					</div>

					<div className="form-split">
						<div className="card">
							<h3 style={{ margin: "0 0 var(--md)" }}>Library details</h3>
							<div
								className="doc-req-row"
								style={{ gridTemplateColumns: "2fr 1fr" }}
							>
								<FormField
									label="Library name"
									help="Top-level folder under documentations/ (the library root)."
								>
									<input
										className="form-control"
										value={libraryName}
										required
										placeholder="MyDatabase"
										onChange={(e) => setLibraryName(e.target.value)}
									/>
								</FormField>
								<FormField label="Library type">
									<select
										className="form-control"
										value={sourceDocType}
										onChange={(e) => setSourceDocType(e.target.value)}
									>
										{(opts?.library_doc_types ?? []).map((t) => (
											<option key={t.value} value={t.value}>
												{t.label}
											</option>
										))}
									</select>
								</FormField>
							</div>
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
