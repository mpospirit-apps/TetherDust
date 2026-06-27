import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  createDatabase,
  getDatabase,
  getEngines,
  updateDatabase,
  type DatabaseInput,
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

export function DatabaseFormPage() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  const engines = useQuery({ queryKey: ["admin", "db-engines"], queryFn: getEngines });
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
    if (isEdit) return;
    const data = engines.data;
    if (!data) return;
    setForm((f) => {
      if (f.port !== "") return f;
      const dp = data.default_ports[f.engine];
      return dp == null ? f : { ...f, port: String(dp) };
    });
  }, [engines.data, isEdit]);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function onEngineChange(value: string) {
    setForm((f) => {
      const dp = engines.data?.default_ports[value];
      const nextPort = !isEdit && f.port === "" && dp != null ? String(dp) : f.port;
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
    onError: (err) => setError(err instanceof Error ? err.message : "Save failed"),
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

  const engineChoices = engines.data?.choices ?? [{ value: form.engine, label: form.engine }];

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>{isEdit ? `Edit ${form.name}` : "Add Database Connection"}</h1>
          <p>Configure a database connection for MCP tools</p>
        </div>
        <Link to="/admin/databases" className="btn btn-ghost">
          Back
        </Link>
      </div>

      {error && (
        <div className="flash flash-error" style={{ marginBottom: "var(--md)" }}>
          {error}
        </div>
      )}

      <form onSubmit={onSubmit}>
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
                  onChange={(e) => set("port", e.target.value)}
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
                help={isEdit ? "Leave blank to keep existing." : "Encrypted at rest."}
              >
                <input
                  className="form-control"
                  type="password"
                  autoComplete="new-password"
                  placeholder={isEdit ? "••••••••  (leave blank to keep)" : "Enter password"}
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
            <FormField label="Extra options (JSON)" help='e.g. {"sslmode": "require"}'>
              <textarea
                className="form-control"
                rows={3}
                value={form.extra_options}
                onChange={(e) => set("extra_options", e.target.value)}
              />
            </FormField>
          </div>
        </div>

        <div className="form-actions" style={{ marginTop: "var(--md)" }}>
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? "Saving…" : isEdit ? "Save Changes" : "Create Connection"}
          </button>
          <Link to="/admin/databases" className="btn btn-secondary">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
