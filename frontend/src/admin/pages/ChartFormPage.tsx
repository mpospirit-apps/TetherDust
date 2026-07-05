import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { listDatabases } from "../../api/admin";
import { apiErrorDetail } from "../../api/client";
import {
	type AdminChartInput,
	createChart,
	getAdminChartData,
	getChart,
	previewChart,
	updateChart,
} from "../../api/dashboards";
import { buildTheme, runChartCode } from "../../charts/render";
import { useChartEditSocket } from "../../charts/useChartEditSocket";
import { useTheme } from "../../hooks/useTheme";
import { FormCheckbox, FormField } from "../components/forms";

const MONO = { fontFamily: "var(--font-mono, monospace)", fontSize: 13 };
const WIDTHS = [
	{ value: 3, label: "Quarter" },
	{ value: 4, label: "Third" },
	{ value: 6, label: "Half" },
	{ value: 8, label: "Two-thirds" },
	{ value: 12, label: "Full" },
];

interface FormState {
	title: string;
	description: string;
	database: string;
	sql_query: string;
	custom_d3_code: string;
	width: number;
	height: number;
	position: number;
	is_active: boolean;
}

const EMPTY: FormState = {
	title: "",
	description: "",
	database: "",
	sql_query: "",
	custom_d3_code: "",
	width: 6,
	height: 300,
	position: 0,
	is_active: true,
};

interface PreviewData {
	columns: string[];
	data: Record<string, unknown>[];
}

export function ChartFormPage() {
	const { dashId, chartId } = useParams();
	const dashboardId = dashId as string;
	const isEdit = Boolean(chartId);
	const navigate = useNavigate();
	const queryClient = useQueryClient();
	const { theme } = useTheme();

	const [form, setForm] = useState<FormState>(EMPTY);
	const [error, setError] = useState<string | null>(null);
	const [previewData, setPreviewData] = useState<PreviewData | null>(null);
	const [previewError, setPreviewError] = useState<string | null>(null);
	const [previewStatus, setPreviewStatus] = useState("");

	const previewRef = useRef<HTMLDivElement>(null);
	const formRef = useRef(form);
	formRef.current = form;

	const databases = useQuery({
		queryKey: ["admin", "databases"],
		queryFn: listDatabases,
	});
	const existing = useQuery({
		queryKey: ["admin", "charts", "detail", chartId],
		queryFn: () => getChart(chartId as string),
		enabled: isEdit,
	});
	const cached = useQuery({
		queryKey: ["admin", "chart-data", chartId],
		queryFn: () => getAdminChartData(chartId as string),
		enabled: isEdit,
	});

	function set<K extends keyof FormState>(key: K, value: FormState[K]) {
		setForm((f) => ({ ...f, [key]: value }));
	}

	useEffect(() => {
		const c = existing.data;
		if (!c) return;
		setForm({
			title: c.title,
			description: c.description,
			database: c.database,
			sql_query: c.sql_query,
			custom_d3_code: c.custom_d3_code,
			width: c.width,
			height: c.height,
			position: c.position,
			is_active: c.is_active,
		});
	}, [existing.data]);

	useEffect(() => {
		if (cached.data && !cached.data.error && cached.data.data) {
			setPreviewData({ columns: cached.data.columns, data: cached.data.data });
			setPreviewStatus(`${cached.data.data.length} rows · cached`);
		}
	}, [cached.data]);

	// (Re)render the live preview (debounced) when data, code, or theme changes.
	useEffect(() => {
		const el = previewRef.current;
		if (!el) return;
		const timer = setTimeout(() => {
			if (!previewData) {
				el.innerHTML =
					'<div class="chart-preview-empty">Click <strong>Run Query</strong> first to load data.</div>';
				return;
			}
			const code = form.custom_d3_code.trim();
			if (!code) {
				el.innerHTML =
					'<div class="chart-preview-empty">Write d3 code to render the chart.</div>';
				return;
			}
			const err = runChartCode(el, code, previewData.data, buildTheme(theme));
			setPreviewError(err ? `Render error: ${err}` : null);
		}, 300);
		return () => clearTimeout(timer);
	}, [previewData, form.custom_d3_code, theme]);

	const runQuery = useMutation({
		mutationFn: ({ database, sql }: { database: string; sql: string }) =>
			previewChart(database, sql),
		onMutate: () => {
			setPreviewError(null);
			setPreviewStatus("Running…");
		},
		onSuccess: (res) => {
			setPreviewData({ columns: res.columns, data: res.data });
			setPreviewStatus(`${res.data.length} rows · just now`);
		},
		onError: (err) => {
			setPreviewData(null);
			setPreviewStatus("Error");
			setPreviewError(apiErrorDetail(err, "Query failed."));
		},
	});

	function onRunQuery() {
		if (!form.database) {
			setPreviewError("Pick a database first.");
			return;
		}
		if (!form.sql_query.trim()) {
			setPreviewError("Enter a SQL query first.");
			return;
		}
		runQuery.mutate({ database: form.database, sql: form.sql_query.trim() });
	}

	// After an AI turn, re-read the chart's saved state and refresh the preview.
	async function reloadChartState() {
		if (!chartId) return;
		const fresh = await getChart(chartId);
		const sqlChanged = fresh.sql_query !== formRef.current.sql_query;
		setForm((f) => ({
			...f,
			title: fresh.title,
			description: fresh.description,
			sql_query: fresh.sql_query,
			custom_d3_code: fresh.custom_d3_code,
		}));
		if (sqlChanged && fresh.database && fresh.sql_query) {
			runQuery.mutate({ database: fresh.database, sql: fresh.sql_query });
		}
	}

	const save = useMutation({
		mutationFn: (payload: AdminChartInput) =>
			isEdit ? updateChart(chartId as string, payload) : createChart(payload),
		onSuccess: () => {
			queryClient.invalidateQueries({
				queryKey: ["admin", "charts", dashboardId],
			});
			navigate(`/admin/dashboards/${dashboardId}`);
		},
		onError: (err) => setError(apiErrorDetail(err, "Save failed.")),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		save.mutate({
			dashboard: dashboardId,
			database: form.database,
			title: form.title,
			description: form.description,
			sql_query: form.sql_query,
			custom_d3_code: form.custom_d3_code,
			width: form.width,
			height: form.height,
			position: form.position,
			is_active: form.is_active,
		});
	}

	const dbOptions = databases.data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>{isEdit ? `Edit ${form.title}` : "Add Chart"}</h1>
					<p>
						Write a read-only SQL query and the d3 code that renders its result
					</p>
				</div>
				<div className="form-actions">
					<Link
						to={`/admin/dashboards/${dashboardId}`}
						className="btn btn-ghost"
					>
						Cancel
					</Link>
					<button
						type="submit"
						form="chart-form"
						className="btn btn-primary"
						disabled={save.isPending}
					>
						{save.isPending
							? "Saving…"
							: isEdit
								? "Save Changes"
								: "Create Chart"}
					</button>
				</div>
			</div>

			{error && (
				<div
					className="flash flash-error"
					style={{ marginBottom: "var(--md)" }}
				>
					{error}
				</div>
			)}

			<form id="chart-form" onSubmit={onSubmit}>
				<div className="chart-edit-grid">
					<div className="card">
						<FormField label="Title">
							<input
								className="form-control"
								value={form.title}
								required
								onChange={(e) => set("title", e.target.value)}
							/>
						</FormField>
						<FormField label="Description">
							<textarea
								className="form-control"
								rows={2}
								value={form.description}
								onChange={(e) => set("description", e.target.value)}
							/>
						</FormField>
						<FormField label="Database">
							<select
								className="form-control"
								value={form.database}
								required
								onChange={(e) => set("database", e.target.value)}
							>
								<option value="">— Select a database —</option>
								{dbOptions.map((d) => (
									<option key={d.id} value={d.id}>
										{d.name}
									</option>
								))}
							</select>
						</FormField>
						<FormField
							label="SQL query"
							help="Read-only SELECT that produces the chart data."
						>
							<textarea
								className="form-control"
								rows={8}
								style={MONO}
								value={form.sql_query}
								placeholder={
									"SELECT column1, column2\nFROM table_name\nWHERE condition"
								}
								onChange={(e) => set("sql_query", e.target.value)}
							/>
						</FormField>
						<FormField
							label="Custom d3 code"
							help="Receives (data, container, d3, theme). Use d3.select(container) as the root."
						>
							<textarea
								className="form-control"
								rows={16}
								style={MONO}
								value={form.custom_d3_code}
								onChange={(e) => set("custom_d3_code", e.target.value)}
							/>
						</FormField>

						<div className="form-grid">
							<FormField label="Width">
								<select
									className="form-control"
									value={form.width}
									onChange={(e) => set("width", Number(e.target.value))}
								>
									{WIDTHS.map((w) => (
										<option key={w.value} value={w.value}>
											{w.label} ({w.value}/12)
										</option>
									))}
								</select>
							</FormField>
							<FormField label="Height (px)">
								<input
									type="number"
									className="form-control"
									value={form.height}
									onChange={(e) => set("height", Number(e.target.value))}
								/>
							</FormField>
							<FormField label="Position">
								<input
									type="number"
									className="form-control"
									value={form.position}
									onChange={(e) => set("position", Number(e.target.value))}
								/>
							</FormField>
						</div>
						<FormCheckbox
							label="Is active"
							checked={form.is_active}
							onChange={(v) => set("is_active", v)}
						/>
					</div>

					<div className="chart-edit-sidebar">
						<div className="chart-preview-card">
							<div className="chart-preview-card__header">
								<strong>Preview</strong>
								<div className="chart-preview-card__meta">
									<span>{previewStatus}</span>
									<button
										type="button"
										className="btn btn-secondary btn-sm"
										disabled={runQuery.isPending}
										onClick={onRunQuery}
									>
										{runQuery.isPending ? "Running…" : "Run Query"}
									</button>
								</div>
							</div>
							<div className="chart-preview-card__body">
								<div
									className="chart-preview-container"
									ref={previewRef}
									style={{ height: `${form.height}px` }}
								/>
								{previewError && (
									<div className="chart-preview-error is-visible">
										{previewError}
									</div>
								)}
							</div>
						</div>

						{isEdit && chartId && (
							<ChartAiPanel chartId={chartId} onDone={reloadChartState} />
						)}
					</div>
				</div>
			</form>
		</div>
	);
}

function ChartAiPanel({
	chartId,
	onDone,
}: {
	chartId: string;
	onDone: () => void;
}) {
	const { messages, streaming, statusText, connected, send } =
		useChartEditSocket({
			chartId,
			onDone,
		});
	const [input, setInput] = useState("");
	const transcriptRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (messages.length === 0 && !statusText) return;
		const el = transcriptRef.current;
		if (el) el.scrollTop = el.scrollHeight;
	}, [messages, statusText]);

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		if (!input.trim() || streaming) return;
		send(input);
		setInput("");
	}

	return (
		<div className="chart-aichat-card">
			<div className="chart-aichat-card__header">
				<strong>AI editor</strong>
				<span
					style={{ color: connected ? "var(--c-lime)" : "var(--text-muted)" }}
				>
					{connected ? "Connected" : "connecting…"}
				</span>
			</div>
			<div className="chart-aichat-transcript" ref={transcriptRef}>
				{messages.length === 0 ? (
					<div className="chart-aichat-empty">
						<div className="chart-aichat-empty__intro">
							Ask the agent to tweak the query or the d3 code — e.g. “make it a
							horizontal bar chart” or “group by month”.
						</div>
					</div>
				) : (
					messages.map((m) => (
						<div
							key={m.id}
							className={`chart-aichat-msg chart-aichat-msg--${m.role}`}
						>
							<div className="chart-aichat-msg__label">
								{m.role === "user"
									? "You"
									: m.role === "assistant"
										? "Agent"
										: "Error"}
							</div>
							<div>{m.content || (m.pending ? "…" : "")}</div>
						</div>
					))
				)}
				{streaming && statusText && (
					<div className="chart-aichat-msg chart-aichat-msg--assistant">
						<div className="chart-aichat-msg__label">Agent</div>
						<div className="text-sec text-sm">{statusText}</div>
					</div>
				)}
			</div>
			<form className="chart-aichat-form" onSubmit={onSubmit}>
				<input
					className="form-control"
					placeholder="Ask the AI to edit this chart…"
					value={input}
					disabled={streaming}
					onChange={(e) => setInput(e.target.value)}
				/>
				<button
					type="submit"
					className="btn btn-primary btn-sm"
					disabled={streaming || !connected}
				>
					Send
				</button>
			</form>
		</div>
	);
}
