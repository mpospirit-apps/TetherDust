import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
  createMCPServer,
  getMCPServer,
  updateMCPServer,
  type MCPServerInput,
} from "../../api/mcp";
import { FormCheckbox, FormField } from "../components/forms";

interface FormState {
  name: string;
  description: string;
  transport: string;
  url: string;
  auth_token: string;
  headers: string;
  command: string;
  args: string;
  command_env: string;
  is_active: boolean;
}

const EMPTY: FormState = {
  name: "",
  description: "",
  transport: "streamable-http",
  url: "",
  auth_token: "",
  headers: "",
  command: "",
  args: "",
  command_env: "",
  is_active: true,
};

const MONO = { fontFamily: "var(--font-mono, monospace)", fontSize: 13 };

export function MCPServerFormPage() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [form, setForm] = useState<FormState>(EMPTY);
  const [hasToken, setHasToken] = useState(false);
  const [hasEnv, setHasEnv] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const existing = useQuery({
    queryKey: ["admin", "mcp-servers", id],
    queryFn: () => getMCPServer(id as string),
    enabled: isEdit,
  });

  useEffect(() => {
    const s = existing.data;
    if (!s) return;
    setForm({
      name: s.name,
      description: s.description,
      transport: s.transport || "streamable-http",
      url: s.url,
      auth_token: "",
      headers:
        s.headers && Object.keys(s.headers).length ? JSON.stringify(s.headers, null, 2) : "",
      command: s.command,
      args: Array.isArray(s.args) && s.args.length ? JSON.stringify(s.args, null, 2) : "",
      command_env: "",
      is_active: s.is_active,
    });
    setHasToken(s.has_auth_token);
    setHasEnv(s.has_command_env);
  }, [existing.data]);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  const save = useMutation({
    mutationFn: (payload: MCPServerInput) =>
      isEdit ? updateMCPServer(id as string, payload) : createMCPServer(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "mcp-servers"] });
      navigate("/admin/mcp-servers");
    },
    onError: (err) => setError(apiErrorDetail(err, "Save failed.")),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    let headers: Record<string, unknown> = {};
    if (form.headers.trim()) {
      try {
        headers = JSON.parse(form.headers);
      } catch {
        setError("Headers must be valid JSON (an object).");
        return;
      }
    }
    let args: unknown[] = [];
    if (form.args.trim()) {
      try {
        args = JSON.parse(form.args);
      } catch {
        setError("Args must be valid JSON (an array).");
        return;
      }
    }

    const payload: MCPServerInput = {
      name: form.name,
      description: form.description,
      transport: form.transport,
      url: form.url.trim(),
      headers,
      command: form.command.trim(),
      args,
      is_active: form.is_active,
    };
    if (form.auth_token) payload.auth_token = form.auth_token;
    if (form.command_env.trim()) payload.command_env = form.command_env;
    save.mutate(payload);
  }

  if (isEdit && existing.isLoading) {
    return (
      <div className="card">
        <p className="text-sec">Loading…</p>
      </div>
    );
  }
  if (isEdit && existing.data?.is_builtin) {
    return (
      <div className="card">
        <p className="text-sec">Built-in servers cannot be edited.</p>
        <Link to={`/admin/mcp-servers/${id}`} className="btn btn-secondary mt-md">
          Back to server
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>{isEdit ? `Edit ${form.name}` : "Add MCP Server"}</h1>
          <p>Set a URL (remote HTTP) or a command (local subprocess) — not both.</p>
        </div>
        <Link to="/admin/mcp-servers" className="btn btn-ghost">
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
              label="Is active"
              checked={form.is_active}
              onChange={(v) => set("is_active", v)}
            />
          </div>

          <div className="card">
            <h3 style={{ margin: "0 0 var(--md)" }}>Remote (HTTP)</h3>
            <FormField label="URL" help="Full MCP endpoint, e.g. https://example.com/mcp">
              <input
                className="form-control"
                value={form.url}
                placeholder="https://example.com/mcp"
                onChange={(e) => set("url", e.target.value)}
              />
            </FormField>
            <FormField label="Transport">
              <select
                className="form-control"
                value={form.transport}
                onChange={(e) => set("transport", e.target.value)}
              >
                <option value="streamable-http">Streamable HTTP</option>
                <option value="sse">SSE</option>
              </select>
            </FormField>
            <FormField
              label="Auth token"
              help={
                hasToken
                  ? "Leave blank to keep existing. Sent as Authorization: Bearer …"
                  : "Sent as Authorization: Bearer …. Encrypted at rest."
              }
            >
              <input
                className="form-control"
                type="password"
                autoComplete="new-password"
                placeholder={hasToken ? "••••••••  (leave blank to keep)" : "Enter bearer token"}
                value={form.auth_token}
                onChange={(e) => set("auth_token", e.target.value)}
              />
            </FormField>
            <FormField label="Headers (JSON)" help='Extra HTTP headers, e.g. {"X-API-Key": "..."}'>
              <textarea
                className="form-control"
                rows={3}
                style={MONO}
                placeholder='{"X-API-Key": "..."}'
                value={form.headers}
                onChange={(e) => set("headers", e.target.value)}
              />
            </FormField>
          </div>

          <div className="card">
            <h3 style={{ margin: "0 0 var(--md)" }}>Local (subprocess)</h3>
            <FormField label="Command" help='Executable to run, e.g. "npx" or "uvx".'>
              <input
                className="form-control"
                value={form.command}
                placeholder="npx"
                onChange={(e) => set("command", e.target.value)}
              />
            </FormField>
            <FormField label="Args (JSON)" help='e.g. ["-y", "@notionhq/notion-mcp-server"]'>
              <textarea
                className="form-control"
                rows={2}
                style={MONO}
                placeholder='["-y", "@notionhq/notion-mcp-server"]'
                value={form.args}
                onChange={(e) => set("args", e.target.value)}
              />
            </FormField>
            <FormField
              label="Command env (JSON)"
              help={
                hasEnv
                  ? "Leave blank to keep existing. Encrypted at rest."
                  : 'Env vars for the subprocess, e.g. {"NOTION_API_KEY": "ntn_..."}. Encrypted at rest.'
              }
            >
              <textarea
                className="form-control"
                rows={3}
                style={MONO}
                placeholder={hasEnv ? "••••••••  (leave blank to keep)" : '{"NOTION_API_KEY": "ntn_..."}'}
                value={form.command_env}
                onChange={(e) => set("command_env", e.target.value)}
              />
            </FormField>
          </div>
        </div>

        <div className="form-actions" style={{ marginTop: "var(--md)" }}>
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? "Saving…" : isEdit ? "Save Changes" : "Create Server"}
          </button>
          <Link to="/admin/mcp-servers" className="btn btn-secondary">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
