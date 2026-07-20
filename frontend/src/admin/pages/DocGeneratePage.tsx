import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import Markdown from "react-markdown";
import { Link } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { apiErrorDetail } from "../../api/client";
import {
	getGenerateOptions,
	previewGenerate,
	startGenerate,
} from "../../api/docs";
import { ComboInput, CustomSelect, FormField } from "../components/forms";
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
		description: "Name the page and choose where it's saved.",
	},
	{
		key: "configuration",
		label: "Configuration",
		description: "Pick the type and scope to steer generation.",
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

	// Debounce the Prompt step's live preview so it doesn't refetch on every
	// keystroke — settles 400ms after the last change to any input it depends on.
	const [previewInputs, setPreviewInputs] = useState({
		doc_name: docName,
		doc_type: docType,
		destination,
		scope,
		source_db: sources.databases,
		source_doc: sources.docs,
		source_codebase: sources.codebases,
	});
	useEffect(() => {
		const timer = setTimeout(() => {
			setPreviewInputs({
				doc_name: docName,
				doc_type: docType,
				destination,
				scope,
				source_db: sources.databases,
				source_doc: sources.docs,
				source_codebase: sources.codebases,
			});
		}, 400);
		return () => clearTimeout(timer);
	}, [docName, docType, destination, scope, sources]);

	const preview = useQuery({
		queryKey: ["docgen-preview", previewInputs],
		queryFn: () => previewGenerate(previewInputs),
		placeholderData: keepPreviousData,
	});

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
	const noActiveAgent = Boolean(opts) && !opts?.agents.some((a) => a.is_active);

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
							disabled={start.isPending || noActiveAgent}
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
											Pick a template and scope, then select your data sources
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

					<div className="form-split-col">
						<div className="form-split">
							<div className="wizard-section">
								<WizardSectionHeading step={STEPS[0]} index={0} />
								<div className="card">
									<FormField label="File name" help="Saved as <name>.md.">
										<input
											className="form-control"
											value={docName}
											required
											placeholder="Orders"
											onChange={(e) => setDocName(e.target.value)}
										/>
									</FormField>
									<FormField
										label="Destination folder"
										help="Existing or new folder under /sources/docs/."
									>
										<ComboInput
											value={destination}
											onChange={setDestination}
											options={opts?.dest_folders ?? []}
											placeholder="MyDatabase"
											required
										/>
									</FormField>
								</div>
							</div>

							<div className="wizard-section">
								<WizardSectionHeading step={STEPS[1]} index={1} />
								<div className="card">
									<FormField label="Type">
										<CustomSelect
											value={docType}
											onChange={setDocType}
											options={opts?.doc_types ?? []}
										/>
									</FormField>

									<FormField
										label="Scope & goals"
										help="Steer what the page should cover."
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
