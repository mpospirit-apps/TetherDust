import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import Markdown from "react-markdown";
import { Link } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { apiErrorDetail } from "../../api/client";
import {
	getGenerateOptions,
	previewGenerateLibrary,
	startGenerateLibrary,
} from "../../api/docs";
import { CustomSelect, FormField } from "../components/forms";
import { WizardSectionHeading, type WizardStepDef } from "../components/wizard";
import {
	SourceSelect,
	type SourceSelection,
	StatusPanel,
	useDocGenStatus,
} from "./DocGenShared";

const NO_SOURCES: SourceSelection = { databases: [], docs: [], codebases: [] };

// Identity first, the generation config next, source material last.
const STEPS: WizardStepDef[] = [
	{
		key: "identity",
		label: "Identity",
		description: "Name the library — this becomes its root folder.",
	},
	{
		key: "configuration",
		label: "Configuration",
		description: "Pick the library type and scope to steer generation.",
	},
	{
		key: "sources",
		label: "Sources",
		description: "Select the databases, docs, and codebases to generate from.",
	},
	{
		key: "prompt",
		label: "Prompt",
		description: "Preview the exact prompt that will be sent to the agent.",
	},
];

export function DocLibraryPage() {
	const options = useQuery({
		queryKey: ["admin", "docsource-options"],
		queryFn: getGenerateOptions,
	});

	const [libraryName, setLibraryName] = useState("");
	const [sourceDocType, setSourceDocType] = useState("database");
	const [scope, setScope] = useState("");
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

	// Debounce the Prompt step's live preview so it doesn't refetch on every
	// keystroke — settles 400ms after the last change to any input it depends on.
	const [previewInputs, setPreviewInputs] = useState({
		library_name: libraryName,
		source_doc_type: sourceDocType,
		scope,
		source_db: sources.databases,
		source_doc: sources.docs,
		source_codebase: sources.codebases,
	});
	useEffect(() => {
		const timer = setTimeout(() => {
			setPreviewInputs({
				library_name: libraryName,
				source_doc_type: sourceDocType,
				scope,
				source_db: sources.databases,
				source_doc: sources.docs,
				source_codebase: sources.codebases,
			});
		}, 400);
		return () => clearTimeout(timer);
	}, [libraryName, sourceDocType, scope, sources]);

	const preview = useQuery({
		queryKey: ["docgen-library-preview", previewInputs],
		queryFn: () => previewGenerateLibrary(previewInputs),
		placeholderData: keepPreviousData,
	});

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
			scope,
			agent,
			source_db: sources.databases,
			source_doc: sources.docs,
			source_codebase: sources.codebases,
		});
	}

	const opts = options.data;
	const noActiveAgent = Boolean(opts) && !opts?.agents.some((a) => a.is_active);

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
							disabled={start.isPending || noActiveAgent}
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
									setScope("");
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
											Name the library and scope, then select your data sources
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

					<div className="form-split-col">
						<div className="form-split">
							<div className="wizard-section">
								<WizardSectionHeading step={STEPS[0]} index={0} />
								<div className="card">
									<FormField
										label="Library name"
										help="Top-level folder under /sources/docs/ (the library root)."
									>
										<input
											className="form-control"
											value={libraryName}
											required
											placeholder="MyDatabase"
											onChange={(e) => setLibraryName(e.target.value)}
										/>
									</FormField>
								</div>
							</div>

							<div className="wizard-section">
								<WizardSectionHeading step={STEPS[1]} index={1} />
								<div className="card">
									<FormField label="Library type">
										<CustomSelect
											value={sourceDocType}
											onChange={setSourceDocType}
											options={opts?.library_doc_types ?? []}
										/>
									</FormField>

									<FormField
										label="Scope & goals"
										help="Steer what the library should cover."
									>
										<textarea
											className="form-control"
											rows={3}
											value={scope}
											onChange={(e) => setScope(e.target.value)}
										/>
									</FormField>
								</div>
							</div>
						</div>

						<div className="wizard-section">
							<WizardSectionHeading step={STEPS[2]} index={2} />
							<div className="card">
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

						<div className="wizard-section">
							<WizardSectionHeading step={STEPS[3]} index={3} />
							<div className="card">
								<FormField
									label="Prompt"
									help="Read-only — updates automatically as the fields above change."
								>
									<div className="doc-result-preview__content">
										<Markdown remarkPlugins={[remarkGfm]}>
											{preview.isLoading
												? "_Loading preview…_"
												: preview.data?.prompt || "_(empty)_"}
										</Markdown>
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
