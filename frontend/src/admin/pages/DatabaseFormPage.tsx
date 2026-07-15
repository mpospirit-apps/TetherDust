import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
	createDatabase,
	type DatabaseInput,
	type EngineChoice,
	getDatabase,
	getEngines,
	getSqliteFiles,
	type TestResult,
	testDraftDatabase,
	updateDatabase,
} from "../../api/admin";
import {
	DEFAULT_ENGINE_META,
	ENGINE_META,
	EngineIconGlyph,
} from "../components/engineIcons";
import { FormField, ToggleField } from "../components/forms";
import { WizardSectionHeading, type WizardStepDef } from "../components/wizard";

interface FormState {
	name: string;
	description: string;
	engine: string;
	host: string;
	port: string;
	database: string;
	username: string;
	password: string;
	connection_string: string;
	extra_options: string;
	read_only: boolean;
	is_active: boolean;
}

const EMPTY: FormState = {
	name: "",
	description: "",
	engine: "postgresql",
	host: "",
	port: "",
	database: "",
	username: "",
	password: "",
	connection_string: "",
	extra_options: "",
	read_only: true,
	is_active: true,
};

// Deep-links straight to the repo's "Database support request" issue
// template (.github/ISSUE_TEMPLATE/database_support.md) instead of the
// generic issues list.
const GITHUB_DATABASE_REQUEST_URL =
	"https://github.com/mpospirit-apps/TetherDust/issues/new?template=database_support.md";

// Groups the step-1 engine picker into labeled sections (row-based SQL
// engines vs. columnar/analytical ones). Any engine the backend returns that
// isn't listed here still shows up, under "Other", so new engines never
// silently disappear from the picker.
const ENGINE_GROUPS: { title: string; values: string[] }[] = [
	{
		title: "Relational",
		values: ["postgresql", "mysql", "mariadb", "mssql", "sqlite"],
	},
	{ title: "Analytical", values: ["clickhouse"] },
];

function groupEngineChoices(
	choices: EngineChoice[],
): { title: string; choices: EngineChoice[] }[] {
	const byValue = new Map(choices.map((c) => [c.value, c]));
	const grouped = ENGINE_GROUPS.map((g) => ({
		title: g.title,
		choices: g.values
			.map((v) => byValue.get(v))
			.filter((c): c is EngineChoice => c != null),
	})).filter((g) => g.choices.length > 0);

	const groupedValues = new Set(ENGINE_GROUPS.flatMap((g) => g.values));
	const other = choices.filter((c) => !groupedValues.has(c.value));
	if (other.length > 0) grouped.push({ title: "Other", choices: other });
	return grouped;
}

// Steps 2+ of the form, shared by both the create and edit layouts (step 1's
// card grid only appears in the create flow, handled separately below).
const STEPS: WizardStepDef[] = [
	{
		key: "identity",
		label: "Identity & Status",
		description:
			"Name the connection and set whether it's read-only and active.",
	},
	{
		key: "host",
		label: "Host & Database",
		description:
			"Enter the engine's host, port, credentials, and target database.",
	},
	{
		key: "optional",
		label: "Optional Configurations",
		description:
			"Optional — override the connection fields with a full URL, or pass engine-specific arguments as JSON.",
	},
];

// Mini "how to" steps shown under the SQLite file picker, styled like the
// wizard section headings above but in blue to read as a nested aside.
const SQLITE_HINT_STEPS: WizardStepDef[] = [
	{
		key: "place",
		label: "Place the file",
		description:
			"Drop your .db/.sqlite file into sources/databases/ at the project root.",
	},
	{
		key: "select",
		label: "Select it",
		description: "Pick it from the dropdown above.",
	},
];

export function DatabaseFormPage() {
	const { id } = useParams();
	const isEdit = Boolean(id);
	const navigate = useNavigate();
	const queryClient = useQueryClient();

	const [form, setForm] = useState<FormState>(EMPTY);
	const [error, setError] = useState<string | null>(null);
	const [testResult, setTestResult] = useState<TestResult | null>(null);
	const [howItWorksOpen, setHowItWorksOpen] = useState(false);
	// Create flow, step 1: pick an engine before showing the connection form.
	const [enginePicked, setEnginePicked] = useState(isEdit);
	// Tracks whether the admin has typed a port themselves, so switching
	// engines keeps updating the auto-filled default until they do.
	const [portTouched, setPortTouched] = useState(false);
	// SQLite is a local file, not a network service — it has no host, port,
	// or credentials, only a file path (stored in the `database` field).
	const isSqlite = form.engine === "sqlite";

	const engines = useQuery({
		queryKey: ["admin", "db-engines"],
		queryFn: getEngines,
	});
	const existing = useQuery({
		queryKey: ["admin", "databases", id],
		queryFn: () => getDatabase(id as string),
		enabled: isEdit,
	});
	const sqliteFiles = useQuery({
		queryKey: ["admin", "db-sqlite-files"],
		queryFn: getSqliteFiles,
		enabled: isSqlite,
	});

	// Populate the form when editing an existing connection.
	useEffect(() => {
		const d = existing.data;
		if (!d) return;
		setForm({
			name: d.name,
			description: d.description,
			engine: d.engine,
			host: d.host,
			port: d.port == null ? "" : String(d.port),
			database: d.database,
			username: d.username,
			password: "",
			connection_string: d.connection_string,
			extra_options:
				d.extra_options && Object.keys(d.extra_options).length
					? JSON.stringify(d.extra_options, null, 2)
					: "",
			read_only: d.read_only,
			is_active: d.is_active,
		});
	}, [existing.data]);

	// Prefill the default port for the initial engine when creating.
	useEffect(() => {
		if (isEdit || portTouched) return;
		const data = engines.data;
		if (!data) return;
		setForm((f) => {
			const dp = data.default_ports[f.engine];
			return dp == null ? f : { ...f, port: String(dp) };
		});
	}, [engines.data, isEdit, portTouched]);

	function set<K extends keyof FormState>(key: K, value: FormState[K]) {
		setForm((f) => ({ ...f, [key]: value }));
	}

	function onEngineChange(value: string) {
		setForm((f) => {
			// SQLite hides host/port/username/password — clear them so a prior
			// engine's values aren't silently kept and submitted alongside it.
			if (value === "sqlite") {
				return {
					...f,
					engine: value,
					host: "",
					port: "",
					username: "",
					password: "",
				};
			}
			const dp = engines.data?.default_ports[value];
			const nextPort =
				!isEdit && !portTouched ? (dp == null ? "" : String(dp)) : f.port;
			return { ...f, engine: value, port: nextPort };
		});
	}

	const save = useMutation({
		mutationFn: (payload: DatabaseInput) =>
			isEdit ? updateDatabase(id as string, payload) : createDatabase(payload),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["admin", "databases"] });
			navigate("/admin/databases");
		},
		onError: (err) =>
			setError(err instanceof Error ? err.message : "Save failed"),
	});

	const test = useMutation({
		mutationFn: (payload: DatabaseInput & { id?: string }) =>
			testDraftDatabase(payload),
		onSuccess: setTestResult,
		onError: () => setTestResult({ ok: false, detail: "Request failed" }),
	});

	// Shared by Save and Test — returns null (and sets `error`) on bad JSON.
	function buildPayload(): DatabaseInput | null {
		let extra: Record<string, unknown> = {};
		if (form.extra_options.trim()) {
			try {
				extra = JSON.parse(form.extra_options);
			} catch {
				setError("Extra options must be valid JSON.");
				return null;
			}
		}

		const payload: DatabaseInput = {
			name: form.name,
			description: form.description,
			engine: form.engine,
			host: form.host,
			port: form.port.trim() === "" ? null : Number(form.port),
			database: form.database,
			username: form.username,
			connection_string: form.connection_string,
			extra_options: extra,
			read_only: form.read_only,
			is_active: form.is_active,
		};
		if (form.password) {
			payload.password = form.password;
		}
		return payload;
	}

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		setTestResult(null);
		const payload = buildPayload();
		if (payload) save.mutate(payload);
	}

	function onTest() {
		setError(null);
		setTestResult(null);
		const payload = buildPayload();
		if (payload)
			test.mutate(isEdit ? { ...payload, id: id as string } : payload);
	}

	if (isEdit && existing.isLoading) {
		return (
			<div className="card">
				<p className="text-sec">Loading…</p>
			</div>
		);
	}

	const engineChoices = engines.data?.choices ?? [
		{ value: form.engine, label: form.engine },
	];

	// Create flow, step 1: pick an engine.
	if (!isEdit && !enginePicked) {
		return (
			<div>
				<div className="page-header">
					<div>
						<h1>Add Database Connection</h1>
						<p>Choose a database engine</p>
					</div>
					<Link to="/admin/databases" className="btn btn-ghost">
						Back
					</Link>
				</div>
				{engines.isLoading ? (
					<p className="text-sec">Loading…</p>
				) : (
					groupEngineChoices(engineChoices).map((group) => (
						<div className="choice-section" key={group.title}>
							<h3 className="choice-section__title">{group.title}</h3>
							<div className="choice-list choice-list--grid">
								{group.choices.map((c) => {
									const meta = ENGINE_META[c.value] ?? DEFAULT_ENGINE_META;
									return (
										<button
											key={c.value}
											type="button"
											className="choice-card"
											onClick={() => {
												onEngineChange(c.value);
												setEnginePicked(true);
											}}
										>
											<EngineIconGlyph icon={meta.icon} />
											<div className="choice-card__body">
												<h4>{c.label}</h4>
												{meta.blurb && <p>{meta.blurb}</p>}
											</div>
											<i className="fa-solid fa-chevron-right choice-card__chevron" />
										</button>
									);
								})}
							</div>
						</div>
					))
				)}
				<div className="choice-section">
					<h3 className="choice-section__title">
						Not finding what you're looking for?
					</h3>
					<div className="choice-list choice-list--grid">
						<a
							href={GITHUB_DATABASE_REQUEST_URL}
							target="_blank"
							rel="noopener noreferrer"
							className="choice-card"
						>
							<i className="fa-brands fa-github choice-card__icon" />
							<div className="choice-card__body">
								<h4>Request a database engine</h4>
								<p>
									Open a feature request on GitHub if your database isn't
									listed.
								</p>
							</div>
							<i className="fa-solid fa-arrow-up-right-from-square choice-card__chevron" />
						</a>
					</div>
				</div>
			</div>
		);
	}

	const engineLabel =
		engineChoices.find((c) => c.value === form.engine)?.label ?? form.engine;
	const engineMeta = ENGINE_META[form.engine] ?? DEFAULT_ENGINE_META;
	const hostStep = isSqlite
		? { ...STEPS[1], description: "Enter the path to the SQLite file." }
		: STEPS[1];
	const sqliteFileList = sqliteFiles.data?.files ?? [];
	// If the stored path isn't among the discovered files (deleted, or set
	// before this picker existed), keep it selectable instead of silently
	// blanking the field.
	const sqliteOptions =
		form.database && !sqliteFileList.some((f) => f.path === form.database)
			? [
					{ name: form.database, path: form.database, used_by: null },
					...sqliteFileList,
				]
			: sqliteFileList;

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>
						<span className="title-icon-tag">
							<EngineIconGlyph icon={engineMeta.icon} />
							{isEdit ? `Edit ${form.name}` : engineLabel}
						</span>
					</h1>
					<p>Configure a database connection for MCP tools</p>
				</div>
				<div className="form-actions">
					<Link to="/admin/databases" className="btn btn-ghost">
						Cancel
					</Link>
					<button
						type="button"
						className="btn btn-secondary"
						disabled={test.isPending}
						onClick={onTest}
					>
						{test.isPending ? (
							<i className="fa-solid fa-spinner fa-spin" />
						) : (
							<>
								<i className="fa-solid fa-plug-circle-check" /> Test
							</>
						)}
					</button>
					<button
						type="submit"
						form="database-form"
						className="btn btn-primary"
						disabled={save.isPending}
					>
						{save.isPending
							? "Saving…"
							: isEdit
								? "Save Changes"
								: "Create Connection"}
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

			{testResult && (
				<div
					className={
						testResult.ok ? "flash flash-success" : "flash flash-error"
					}
					style={{ marginBottom: "var(--md)" }}
				>
					{testResult.ok ? "Connected ✓" : `Failed: ${testResult.detail}`}
				</div>
			)}

			<form id="database-form" onSubmit={onSubmit}>
				{!isEdit && (
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
											<i className="fa-solid fa-database" />
										</div>
										<div className="doc-hiw-label">Connect</div>
										<div className="doc-hiw-desc">
											Point at PostgreSQL, MySQL, MariaDB, SQL Server, SQLite,
											or ClickHouse
										</div>
									</div>
									<div className="doc-hiw-arrow">
										<i className="fa-solid fa-chevron-right" />
									</div>
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-plug-circle-check" />
										</div>
										<div className="doc-hiw-label">Test it</div>
										<div className="doc-hiw-desc">
											Probe connectivity with the current form values before
											saving
										</div>
									</div>
									<div className="doc-hiw-arrow">
										<i className="fa-solid fa-chevron-right" />
									</div>
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-shield-halved" />
										</div>
										<div className="doc-hiw-label">Read-only enforced</div>
										<div className="doc-hiw-desc">
											Every query is SQL-validated and run in a read-only
											session
										</div>
									</div>
									<div className="doc-hiw-arrow">
										<i className="fa-solid fa-chevron-right" />
									</div>
									<div className="doc-hiw-step">
										<div className="doc-hiw-icon">
											<i className="fa-solid fa-magnifying-glass-chart" />
										</div>
										<div className="doc-hiw-label">Agent queries it</div>
										<div className="doc-hiw-desc">
											Roles grant access so the agent can list tables and run
											SELECT queries via MCP
										</div>
									</div>
								</div>
							</div>
						</div>
					</div>
				)}

				<div className="form-split-col">
					<div className="form-split">
						<div className="wizard-section">
							<WizardSectionHeading step={STEPS[0]} index={0} />
							<div className="card">
								<FormField label="Name">
									<input
										className="form-control"
										value={form.name}
										required
										onChange={(e) => set("name", e.target.value)}
									/>
								</FormField>
								<FormField label="Description">
									<textarea
										className="form-control"
										rows={3}
										value={form.description}
										onChange={(e) => set("description", e.target.value)}
									/>
								</FormField>
								<ToggleField
									label="Is active"
									description="Requests can use this connection while it's active."
									checked={form.is_active}
									onChange={(v) => set("is_active", v)}
								/>
								<ToggleField
									label="Read only"
									description="Blocks write queries — only SELECT statements are allowed."
									checked={form.read_only}
									onChange={(v) => set("read_only", v)}
								/>
							</div>
						</div>

						<div className="wizard-section">
							<WizardSectionHeading step={hostStep} index={1} />
							<div className="card">
								{isEdit && (
									<FormField label="Engine">
										<select
											className="form-control"
											value={form.engine}
											onChange={(e) => onEngineChange(e.target.value)}
										>
											{engineChoices.map((c) => (
												<option key={c.value} value={c.value}>
													{c.label}
												</option>
											))}
										</select>
									</FormField>
								)}
								{!isSqlite && (
									<div className="form-grid">
										<FormField label="Host">
											<input
												className="form-control"
												value={form.host}
												onChange={(e) => set("host", e.target.value)}
											/>
										</FormField>
										<FormField label="Port">
											<input
												className="form-control"
												type="number"
												value={form.port}
												onChange={(e) => {
													setPortTouched(true);
													set("port", e.target.value);
												}}
											/>
										</FormField>
									</div>
								)}
								<FormField label={isSqlite ? "File path" : "Database"}>
									{isSqlite ? (
										<select
											className="form-control"
											value={form.database}
											required
											onChange={(e) => set("database", e.target.value)}
										>
											<option value="">— Select a file —</option>
											{sqliteOptions.map((f) => (
												<option key={f.path} value={f.path}>
													{f.name}
													{f.used_by && f.path !== form.database
														? ` (used by ${f.used_by})`
														: ""}
												</option>
											))}
										</select>
									) : (
										<input
											className="form-control"
											value={form.database}
											onChange={(e) => set("database", e.target.value)}
										/>
									)}
									{isSqlite &&
										sqliteFileList.length === 0 &&
										!sqliteFiles.isLoading && (
											<div
												className="flash flash-error"
												style={{ marginTop: "var(--sm)" }}
											>
												No files found in sources/databases/. Drop a .db/.sqlite
												file there first.
											</div>
										)}
									{isSqlite && (
										<div className="sqlite-hint-steps">
											{SQLITE_HINT_STEPS.map((step, i) => (
												<WizardSectionHeading
													key={step.key}
													step={step}
													index={i}
												/>
											))}
										</div>
									)}
								</FormField>
								{!isSqlite && (
									<div className="form-grid">
										<FormField label="Username">
											<input
												className="form-control"
												value={form.username}
												autoComplete="off"
												onChange={(e) => set("username", e.target.value)}
											/>
										</FormField>
										<FormField
											label="Password"
											help={
												isEdit
													? "Leave blank to keep existing."
													: "Encrypted at rest."
											}
										>
											<input
												className="form-control"
												type="password"
												autoComplete="new-password"
												placeholder={
													isEdit
														? "••••••••  (leave blank to keep)"
														: "Enter password"
												}
												value={form.password}
												onChange={(e) => set("password", e.target.value)}
											/>
										</FormField>
									</div>
								)}
							</div>
						</div>
					</div>

					<div className="wizard-section">
						<WizardSectionHeading step={STEPS[2]} index={2} />
						<div className="card">
							<div className="field-pair">
								<FormField
									label="Connection string"
									help="Optional — overrides the fields above, e.g. postgresql://user:pass@host:5432/dbname"
								>
									<textarea
										className="form-control"
										rows={3}
										value={form.connection_string}
										onChange={(e) => set("connection_string", e.target.value)}
									/>
								</FormField>
								<FormField
									label="Extra options (JSON)"
									help='e.g. {"sslmode": "require"}'
								>
									<textarea
										className="form-control"
										rows={3}
										value={form.extra_options}
										onChange={(e) => set("extra_options", e.target.value)}
									/>
								</FormField>
							</div>
						</div>
					</div>
				</div>
			</form>
		</div>
	);
}
