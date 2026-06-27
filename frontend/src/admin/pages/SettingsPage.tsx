import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import {
  getGeneralSettings,
  getSmtpSettings,
  testSmtp,
  updateGeneralSettings,
  updateSmtpSettings,
  type GeneralSettings,
} from "../../api/admin";
import { ApiError } from "../../api/client";
import { FormCheckbox, FormField } from "../components/forms";

function numOrNull(value: string): number | null {
  return value.trim() === "" ? null : Number(value);
}

function smtpErrorText(err: unknown): string {
  if (err instanceof ApiError && err.data && typeof err.data === "object" && "error" in err.data) {
    return String((err.data as Record<string, unknown>).error);
  }
  return "Test failed.";
}

function GeneralSettingsCard() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "settings", "general"],
    queryFn: getGeneralSettings,
  });
  const [form, setForm] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!data) return;
    setForm({
      codex_service_url: data.codex_service_url ?? "",
      mcp_base_url: data.mcp_base_url ?? "",
      docgen_timeout: data.docgen_timeout == null ? "" : String(data.docgen_timeout),
      doclibgen_timeout: data.doclibgen_timeout == null ? "" : String(data.doclibgen_timeout),
      chartgen_timeout: data.chartgen_timeout == null ? "" : String(data.chartgen_timeout),
      max_row_limit: data.max_row_limit == null ? "" : String(data.max_row_limit),
      hot_reload_interval:
        data.hot_reload_interval == null ? "" : String(data.hot_reload_interval),
    });
  }, [data]);

  const save = useMutation({
    mutationFn: (payload: GeneralSettings) => updateGeneralSettings(payload),
    onSuccess: () => {
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["admin", "settings", "general"] });
      setTimeout(() => setSaved(false), 2500);
    },
  });

  function set(key: string, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate({
      codex_service_url: form.codex_service_url ?? "",
      mcp_base_url: form.mcp_base_url ?? "",
      docgen_timeout: numOrNull(form.docgen_timeout ?? ""),
      doclibgen_timeout: numOrNull(form.doclibgen_timeout ?? ""),
      chartgen_timeout: numOrNull(form.chartgen_timeout ?? ""),
      max_row_limit: numOrNull(form.max_row_limit ?? ""),
      hot_reload_interval: numOrNull(form.hot_reload_interval ?? ""),
    });
  }

  if (isLoading) {
    return (
      <div className="card">
        <p className="text-sec">Loading…</p>
      </div>
    );
  }

  return (
    <form className="card" onSubmit={onSubmit}>
      <h3 style={{ margin: "0 0 var(--md)" }}>General</h3>
      <FormField label="Codex Service URL">
        <input
          className="form-control"
          value={form.codex_service_url ?? ""}
          onChange={(e) => set("codex_service_url", e.target.value)}
        />
      </FormField>
      <FormField label="MCP Base URL">
        <input
          className="form-control"
          value={form.mcp_base_url ?? ""}
          onChange={(e) => set("mcp_base_url", e.target.value)}
        />
      </FormField>
      <div className="form-grid">
        <FormField label="Doc Gen Timeout (s)">
          <input
            className="form-control"
            type="number"
            value={form.docgen_timeout ?? ""}
            onChange={(e) => set("docgen_timeout", e.target.value)}
          />
        </FormField>
        <FormField label="Doc Library Gen Timeout (s)">
          <input
            className="form-control"
            type="number"
            value={form.doclibgen_timeout ?? ""}
            onChange={(e) => set("doclibgen_timeout", e.target.value)}
          />
        </FormField>
      </div>
      <div className="form-grid">
        <FormField label="Chart Gen Timeout (s)">
          <input
            className="form-control"
            type="number"
            value={form.chartgen_timeout ?? ""}
            onChange={(e) => set("chartgen_timeout", e.target.value)}
          />
        </FormField>
        <FormField label="Max Row Limit" help="Blank = no limit.">
          <input
            className="form-control"
            type="number"
            value={form.max_row_limit ?? ""}
            onChange={(e) => set("max_row_limit", e.target.value)}
          />
        </FormField>
      </div>
      <FormField label="Hot Reload Interval (s)" help="Blank to disable.">
        <input
          className="form-control"
          type="number"
          value={form.hot_reload_interval ?? ""}
          onChange={(e) => set("hot_reload_interval", e.target.value)}
        />
      </FormField>
      <div className="form-actions" style={{ marginTop: "var(--md)" }}>
        <button type="submit" className="btn btn-primary" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save General"}
        </button>
        {saved && <span className="badge badge-success">Saved ✓</span>}
      </div>
    </form>
  );
}

interface SmtpForm {
  smtp_host: string;
  smtp_port: string;
  smtp_username: string;
  smtp_password: string;
  smtp_use_tls: boolean;
  smtp_from_email: string;
  email_max_rows: string;
}

const EMPTY_SMTP: SmtpForm = {
  smtp_host: "",
  smtp_port: "",
  smtp_username: "",
  smtp_password: "",
  smtp_use_tls: true,
  smtp_from_email: "",
  email_max_rows: "",
};

function SmtpSettingsCard() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "settings", "smtp"],
    queryFn: getSmtpSettings,
  });
  const [form, setForm] = useState<SmtpForm>(EMPTY_SMTP);
  const [hasPassword, setHasPassword] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testMsg, setTestMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!data) return;
    setForm({
      smtp_host: data.smtp_host ?? "",
      smtp_port: data.smtp_port == null ? "" : String(data.smtp_port),
      smtp_username: data.smtp_username ?? "",
      smtp_password: "",
      smtp_use_tls: data.smtp_use_tls,
      smtp_from_email: data.smtp_from_email ?? "",
      email_max_rows: data.email_max_rows == null ? "" : String(data.email_max_rows),
    });
    setHasPassword(data.has_password);
  }, [data]);

  const save = useMutation({
    mutationFn: () =>
      updateSmtpSettings({
        smtp_host: form.smtp_host,
        smtp_port: numOrNull(form.smtp_port),
        smtp_username: form.smtp_username,
        smtp_use_tls: form.smtp_use_tls,
        smtp_from_email: form.smtp_from_email,
        email_max_rows: numOrNull(form.email_max_rows),
        ...(form.smtp_password ? { smtp_password: form.smtp_password } : {}),
      }),
    onSuccess: () => {
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["admin", "settings", "smtp"] });
      setTimeout(() => setSaved(false), 2500);
    },
  });

  const test = useMutation({
    mutationFn: testSmtp,
    onSuccess: (r) => setTestMsg({ ok: true, text: r.message ?? "Sent." }),
    onError: (err) => setTestMsg({ ok: false, text: smtpErrorText(err) }),
  });

  function set<K extends keyof SmtpForm>(key: K, value: SmtpForm[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate();
  }

  if (isLoading) {
    return (
      <div className="card">
        <p className="text-sec">Loading…</p>
      </div>
    );
  }

  return (
    <form className="card" onSubmit={onSubmit}>
      <h3 style={{ margin: "0 0 var(--md)" }}>Email (SMTP)</h3>
      <div className="form-grid">
        <FormField label="SMTP Host">
          <input
            className="form-control"
            value={form.smtp_host}
            onChange={(e) => set("smtp_host", e.target.value)}
          />
        </FormField>
        <FormField label="SMTP Port">
          <input
            className="form-control"
            type="number"
            value={form.smtp_port}
            onChange={(e) => set("smtp_port", e.target.value)}
          />
        </FormField>
      </div>
      <div className="form-grid">
        <FormField label="Username">
          <input
            className="form-control"
            autoComplete="off"
            value={form.smtp_username}
            onChange={(e) => set("smtp_username", e.target.value)}
          />
        </FormField>
        <FormField label="Password" help={hasPassword ? "Leave blank to keep existing." : undefined}>
          <input
            className="form-control"
            type="password"
            autoComplete="new-password"
            placeholder={hasPassword ? "••••••••  (leave blank to keep)" : "SMTP password"}
            value={form.smtp_password}
            onChange={(e) => set("smtp_password", e.target.value)}
          />
        </FormField>
      </div>
      <FormField label="From Email">
        <input
          className="form-control"
          type="email"
          value={form.smtp_from_email}
          onChange={(e) => set("smtp_from_email", e.target.value)}
        />
      </FormField>
      <FormField label="Max Rows in CSV Attachment">
        <input
          className="form-control"
          type="number"
          value={form.email_max_rows}
          onChange={(e) => set("email_max_rows", e.target.value)}
        />
      </FormField>
      <FormCheckbox
        label="Use TLS"
        checked={form.smtp_use_tls}
        onChange={(v) => set("smtp_use_tls", v)}
      />
      <div className="form-actions" style={{ marginTop: "var(--md)", flexWrap: "wrap" }}>
        <button type="submit" className="btn btn-primary" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save SMTP"}
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={test.isPending}
          onClick={() => {
            setTestMsg(null);
            test.mutate();
          }}
        >
          {test.isPending ? "Sending…" : "Send Test Email"}
        </button>
        {saved && <span className="badge badge-success">Saved ✓</span>}
        {testMsg && (
          <span className={testMsg.ok ? "badge badge-success" : "badge badge-error"}>
            {testMsg.text}
          </span>
        )}
      </div>
    </form>
  );
}

export function SettingsPage() {
  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p>General operational settings and email (SMTP) configuration.</p>
        </div>
      </div>
      <div className="form-split">
        <GeneralSettingsCard />
        <SmtpSettingsCard />
      </div>
    </div>
  );
}
