import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
	siClickhouse,
	siGooglebigquery,
	siMariadb,
	siMysql,
	siPostgresql,
	siSnowflake,
	siSqlite,
} from "simple-icons";
import {
	createDatabase,
	type DatabaseInput,
	getDatabase,
	getEngines,
	updateDatabase,
} from "../../api/admin";
import { FormCheckbox, FormField } from "../components/forms";

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

type EngineIcon =
	| { kind: "logo"; title: string; path: string }
	| { kind: "fa"; family: "solid" | "brands"; icon: string };

const ENGINE_META: Record<string, { icon: EngineIcon; blurb: string }> = {
	postgresql: {
		icon: { kind: "logo", title: siPostgresql.title, path: siPostgresql.path },
		blurb: "Open-source relational database. Default port 5432.",
	},
	mysql: {
		icon: { kind: "logo", title: siMysql.title, path: siMysql.path },
		blurb: "Popular open-source RDBMS. Default port 3306.",
	},
	mariadb: {
		icon: { kind: "logo", title: siMariadb.title, path: siMariadb.path },
		blurb: "MySQL-compatible fork. Default port 3306.",
	},
	mssql: {
		icon: { kind: "fa", family: "brands", icon: "fa-microsoft" },
		blurb: "Microsoft SQL Server. Default port 1433.",
	},
	oracle: {
		icon: { kind: "fa", family: "solid", icon: "fa-database" },
		blurb: "Oracle Database. Default port 1521.",
	},
	sqlite: {
		icon: { kind: "logo", title: siSqlite.title, path: siSqlite.path },
		blurb: "Local file-based database — no host required.",
	},
	clickhouse: {
		icon: { kind: "logo", title: siClickhouse.title, path: siClickhouse.path },
		blurb: "Columnar OLAP database. Default port 8123.",
	},
	snowflake: {
		icon: { kind: "logo", title: siSnowflake.title, path: siSnowflake.path },
		blurb: "Cloud data warehouse — configure via connection string.",
	},
	bigquery: {
		icon: {
			kind: "logo",
			title: siGooglebigquery.title,
			path: siGooglebigquery.path,
		},
		blurb: "Google BigQuery — serverless cloud warehouse.",
	},
};
const DEFAULT_ENGINE_META: { icon: EngineIcon; blurb: string } = {
	icon: { kind: "fa", family: "solid", icon: "fa-database" },
	blurb: "",
};

function EngineIconGlyph({ icon }: { icon: EngineIcon }) {
	if (icon.kind === "logo") {
		return (
			<span className="choice-card__icon choice-card__icon--logo">
				<svg role="img" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
					<title>{icon.title}</title>
					<path d={icon.path} />
				</svg>
			</span>
		);
	}
	return <i className={`fa-${icon.family} ${icon.icon} choice-card__icon`} />;
}

export function DatabaseFormPage() {
	const { id } = useParams();
	const isEdit = Boolean(id);
	const navigate = useNavigate();
	const queryClient = useQueryClient();

	const [form, setForm] = useState<FormState>(EMPTY);
	const [error, setError] = useState<string | null>(null);
	// Create flow, step 1: pick an engine before showing the connection form.
	const [enginePicked, setEnginePicked] = useState(isEdit);
	// Tracks whether the admin has typed a port themselves, so switching
	// engines keeps updating the auto-filled default until they do.
	const [portTouched, setPortTouched] = useState(false);

	const engines = useQuery({
		queryKey: ["admin", "db-engines"],
		queryFn: getEngines,
	});
	const existing = useQuery({
		queryKey: ["admin", "databases", id],
		queryFn: () => getDatabase(id as string),
		enabled: isEdit,
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

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);

		let extra: Record<string, unknown> = {};
		if (form.extra_options.trim()) {
			try {
				extra = JSON.parse(form.extra_options);
			} catch {
				setError("Extra options must be valid JSON.");
				return;
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
		save.mutate(payload);
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
					<div className="choice-list choice-list--grid">
						{engineChoices.map((c) => {
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
				)}
			</div>
		);
	}

	const engineLabel =
		engineChoices.find((c) => c.value === form.engine)?.label ?? form.engine;

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>{isEdit ? `Edit ${form.name}` : "Add Database Connection"}</h1>
					<p>
						{isEdit
							? "Configure a database connection for MCP tools"
							: engineLabel}
					</p>
				</div>
				<div className="form-actions">
					<Link to="/admin/databases" className="btn btn-ghost">
						Cancel
					</Link>
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

			<form id="database-form" onSubmit={onSubmit}>
				<div className="form-split">
					<div className="card">
						<h3 style={{ margin: "0 0 var(--md)" }}>Identity</h3>
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
						<FormCheckbox
							label="Read only"
							checked={form.read_only}
							onChange={(v) => set("read_only", v)}
						/>
						<FormCheckbox
							label="Is active"
							checked={form.is_active}
							onChange={(v) => set("is_active", v)}
						/>
					</div>

					<div className="card">
						<h3 style={{ margin: "0 0 var(--md)" }}>Connection</h3>
						{isEdit ? (
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
						) : (
							<FormField label="Engine">
								<div className="picked-control">
									<span className="type-badge">{engineLabel}</span>
									<button
										type="button"
										className="btn btn-ghost btn-sm"
										onClick={() => setEnginePicked(false)}
									>
										Change
									</button>
								</div>
							</FormField>
						)}
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
						<FormField label="Database">
							<input
								className="form-control"
								value={form.database}
								onChange={(e) => set("database", e.target.value)}
							/>
						</FormField>
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
						<FormField
							label="Connection string"
							help="Optional: full SQLAlchemy URL (overrides the fields above)."
						>
							<textarea
								className="form-control"
								rows={2}
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
			</form>
		</div>
	);
}
