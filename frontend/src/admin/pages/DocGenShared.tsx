import { useQuery } from "@tanstack/react-query";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { type DocGenStatus, getDocGenStatus } from "../../api/docs";

type Option = { id: string; name: string };

// Narrow shapes shared by the docs + dashboard generation option payloads.
interface SourceOptions {
	databases: Option[];
	doc_sources: Option[];
	codebases: Option[];
}
interface AgentOptions {
	agents: { id: string; name: string; is_active: boolean }[];
}

function CheckColumn({
	title,
	options,
	selected,
	onChange,
}: {
	title: string;
	options: Option[];
	selected: string[];
	onChange: (ids: string[]) => void;
}) {
	if (options.length === 0) return null;
	function toggle(id: string) {
		onChange(
			selected.includes(id)
				? selected.filter((x) => x !== id)
				: [...selected, id],
		);
	}
	return (
		<div className="doc-sources-section">
			<h5>{title}</h5>
			<div className="doc-source-checks">
				{options.map((o) => (
					<label key={o.id}>
						<input
							type="checkbox"
							checked={selected.includes(o.id)}
							onChange={() => toggle(o.id)}
						/>
						{o.name}
					</label>
				))}
			</div>
		</div>
	);
}

export interface SourceSelection {
	databases: string[];
	docs: string[];
	codebases: string[];
}

export function SourceSelect({
	options,
	value,
	onChange,
}: {
	options: SourceOptions;
	value: SourceSelection;
	onChange: (next: SourceSelection) => void;
}) {
	const empty =
		options.databases.length === 0 &&
		options.doc_sources.length === 0 &&
		options.codebases.length === 0;
	if (empty) {
		return (
			<p className="text-sec text-sm">
				No databases, docs, or codebases configured yet.
			</p>
		);
	}
	return (
		<div className="doc-sources-columns">
			<CheckColumn
				title="Database"
				options={options.databases}
				selected={value.databases}
				onChange={(ids) => onChange({ ...value, databases: ids })}
			/>
			<CheckColumn
				title="Documentation"
				options={options.doc_sources}
				selected={value.docs}
				onChange={(ids) => onChange({ ...value, docs: ids })}
			/>
			<CheckColumn
				title="Codebase"
				options={options.codebases}
				selected={value.codebases}
				onChange={(ids) => onChange({ ...value, codebases: ids })}
			/>
		</div>
	);
}

export function AgentSelect({
	options,
	value,
	onChange,
}: {
	options: AgentOptions;
	value: string;
	onChange: (id: string) => void;
}) {
	return (
		<select
			className="form-control"
			value={value}
			onChange={(e) => onChange(e.target.value)}
			required
		>
			<option value="">— Select an agent —</option>
			{options.agents.map((a) => (
				<option key={a.id} value={a.id}>
					{a.name}
					{a.is_active ? " (active)" : ""}
				</option>
			))}
		</select>
	);
}

export function useDocGenStatus(logId: string | null) {
	return useQuery({
		queryKey: ["docgen-status", logId],
		queryFn: () => getDocGenStatus(logId as string),
		enabled: Boolean(logId),
		refetchInterval: (query) =>
			query.state.data?.status === "running" ? 2000 : false,
	});
}

function fmtBytes(bytes: number | null | undefined): string {
	if (!bytes) return "—";
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function StatusPanel({ status }: { status: DocGenStatus }) {
	if (status.status === "running") {
		return (
			<div className="doc-loading-state">
				<i className="fa-solid fa-spinner fa-spin" />
				<p>Generating documentation…</p>
				{status.agent_output && (
					<p className="doc-loading-elapsed">
						{status.agent_output.slice(0, 200)}
					</p>
				)}
			</div>
		);
	}

	if (status.status === "failed") {
		return (
			<div className="flash flash-error">
				Generation failed: {status.error || "unknown error"}
			</div>
		);
	}

	const isPartial = status.status === "partial";
	return (
		<div>
			<div
				className={isPartial ? "flash flash-warning" : "flash flash-success"}
			>
				{isPartial
					? "Completed with warnings."
					: "Documentation generated successfully."}
			</div>
			{(status.warnings ?? []).map((w) => (
				<div
					key={w}
					className="flash flash-warning"
					style={{ marginTop: "var(--sm)" }}
				>
					{w}
				</div>
			))}
			<div className="doc-result-grid" style={{ marginTop: "var(--md)" }}>
				<div className="doc-result-summary">
					<p className="text-sec text-sm">Folder</p>
					<p>
						<strong>{status.folder}</strong>
					</p>
					<p className="text-sec text-sm" style={{ marginTop: "var(--sm)" }}>
						{status.is_library ? `${status.file_count ?? 0} files` : "1 file"}
					</p>
					<p>
						{fmtBytes(status.is_library ? status.total_size : status.file_size)}
					</p>
				</div>
				<div className="doc-result-preview">
					{status.is_library ? (
						<>
							<div className="doc-result-preview__title">
								<i className="fa-solid fa-list" /> Files
							</div>
							<ul className="text-sm">
								{(status.files ?? []).map((f) => (
									<li key={f.path} className="text-mono">
										{f.path}{" "}
										<span className="text-sec">({fmtBytes(f.size)})</span>
									</li>
								))}
							</ul>
						</>
					) : (
						<>
							<div className="doc-result-preview__title">
								<i className="fa-solid fa-file-lines" /> Preview
							</div>
							<div className="doc-result-preview__content">
								<Markdown remarkPlugins={[remarkGfm]}>
									{status.content || "_(empty)_"}
								</Markdown>
							</div>
						</>
					)}
				</div>
			</div>
		</div>
	);
}
