import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { listDatabases, listRoles } from "../../api/admin";
import { apiErrorDetail } from "../../api/client";
import {
  createReport,
  getReportDefinition,
  previewReport,
  updateReport,
  type DeliveryMethod,
  type ExecutionResult,
  type ReportDefinitionInput,
  type ScheduleType,
} from "../../api/reports";
import { ReportResultTable } from "../../reports/ReportResultTable";
import { CheckboxGroup, FormCheckbox, FormField } from "../components/forms";

const SCHEDULE_TYPES: { value: ScheduleType; label: string }[] = [
  { value: "manual", label: "Manual" },
  { value: "interval", label: "Every N minutes / hours" },
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
];

const INTERVALS: { value: string; label: string }[] = [
  { value: "5", label: "Every 5 minutes" },
  { value: "10", label: "Every 10 minutes" },
  { value: "15", label: "Every 15 minutes" },
  { value: "30", label: "Every 30 minutes" },
  { value: "60", label: "Every 1 hour" },
  { value: "120", label: "Every 2 hours" },
  { value: "360", label: "Every 6 hours" },
  { value: "720", label: "Every 12 hours" },
];

const WEEKDAYS: { value: string; label: string }[] = [
  { value: "0", label: "Monday" },
  { value: "1", label: "Tuesday" },
  { value: "2", label: "Wednesday" },
  { value: "3", label: "Thursday" },
  { value: "4", label: "Friday" },
  { value: "5", label: "Saturday" },
  { value: "6", label: "Sunday" },
];

const DELIVERY_METHODS: { value: DeliveryMethod; label: string }[] = [
  { value: "in_app", label: "In-app only" },
  { value: "email", label: "Email" },
];

interface FormState {
  name: string;
  description: string;
  database: string;
  sql_query: string;
  schedule_type: ScheduleType;
  schedule_interval_minutes: string;
  schedule_time: string;
  schedule_day_of_week: string;
  schedule_day_of_month: string;
  delivery_method: DeliveryMethod;
  email_recipients: string;
  is_active: boolean;
  allowed_roles: string[];
}

const EMPTY: FormState = {
  name: "",
  description: "",
  database: "",
  sql_query: "",
  schedule_type: "manual",
  schedule_interval_minutes: "",
  schedule_time: "",
  schedule_day_of_week: "",
  schedule_day_of_month: "",
  delivery_method: "in_app",
  email_recipients: "",
  is_active: true,
  allowed_roles: [],
};

function toNumberOrNull(value: string): number | null {
  return value === "" ? null : Number(value);
}

export function ReportFormPage() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ExecutionResult | null>(null);

  const databases = useQuery({ queryKey: ["admin", "databases"], queryFn: listDatabases });
  const roles = useQuery({ queryKey: ["admin", "roles"], queryFn: listRoles });
  const existing = useQuery({
    queryKey: ["admin", "reports", id],
    queryFn: () => getReportDefinition(id as string),
    enabled: isEdit,
  });

  useEffect(() => {
    const r = existing.data;
    if (!r) return;
    setForm({
      name: r.name,
      description: r.description,
      database: r.database,
      sql_query: r.sql_query,
      schedule_type: r.schedule_type,
      schedule_interval_minutes:
        r.schedule_interval_minutes != null ? String(r.schedule_interval_minutes) : "",
      schedule_time: r.schedule_time ? r.schedule_time.slice(0, 5) : "",
      schedule_day_of_week: r.schedule_day_of_week != null ? String(r.schedule_day_of_week) : "",
      schedule_day_of_month: r.schedule_day_of_month != null ? String(r.schedule_day_of_month) : "",
      delivery_method: r.delivery_method === "email" ? "email" : "in_app",
      email_recipients: r.email_recipients.join("\n"),
      is_active: r.is_active,
      allowed_roles: r.allowed_roles,
    });
  }, [existing.data]);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function buildPayload(): ReportDefinitionInput {
    return {
      name: form.name,
      description: form.description,
      database: form.database,
      sql_query: form.sql_query,
      schedule_type: form.schedule_type,
      schedule_interval_minutes:
        form.schedule_type === "interval"
          ? toNumberOrNull(form.schedule_interval_minutes)
          : null,
      schedule_time:
        form.schedule_type === "daily" ||
        form.schedule_type === "weekly" ||
        form.schedule_type === "monthly"
          ? form.schedule_time || null
          : null,
      schedule_day_of_week:
        form.schedule_type === "weekly" ? toNumberOrNull(form.schedule_day_of_week) : null,
      schedule_day_of_month:
        form.schedule_type === "monthly" ? toNumberOrNull(form.schedule_day_of_month) : null,
      delivery_method: form.delivery_method,
      is_active: form.is_active,
      allowed_roles: form.allowed_roles,
      email_recipients:
        form.delivery_method === "email"
          ? form.email_recipients
              .split("\n")
              .map((s) => s.trim())
              .filter(Boolean)
          : [],
    };
  }

  const save = useMutation({
    mutationFn: (payload: ReportDefinitionInput) =>
      isEdit ? updateReport(id as string, payload) : createReport(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "reports"] });
      navigate("/admin/reports");
    },
    onError: (err) => setError(apiErrorDetail(err, "Save failed.")),
  });

  const runPreview = useMutation({
    mutationFn: () => previewReport(id as string),
    onSuccess: (execution) => setPreview(execution),
    onError: (err) => window.alert(apiErrorDetail(err, "Preview failed.")),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    save.mutate(buildPayload());
  }

  const dbOptions = databases.data?.results ?? [];
  const roleOptions = (roles.data?.results ?? []).map((r) => ({ id: r.id, name: r.name }));

  if (isEdit && existing.isLoading) {
    return (
      <div className="card">
        <p className="text-sec">Loading…</p>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>{isEdit ? `Edit ${form.name}` : "New Report"}</h1>
          <p>A read-only SQL query, optionally scheduled and emailed</p>
        </div>
        <Link to="/admin/reports" className="btn btn-ghost">
          Back
        </Link>
      </div>

      {error && (
        <div className="flash flash-error" style={{ marginBottom: "var(--md)" }}>
          {error}
        </div>
      )}

      <form onSubmit={onSubmit} className="card" style={{ maxWidth: 720 }}>
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
            <option value="">— Select —</option>
            {dbOptions.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label="SQL query" help="Read-only SELECT or WITH query.">
          <textarea
            className="form-control"
            rows={12}
            style={{ fontFamily: "var(--font)", fontSize: "13px" }}
            value={form.sql_query}
            required
            onChange={(e) => set("sql_query", e.target.value)}
            placeholder={"SELECT column1, column2\nFROM table_name\nWHERE condition"}
          />
        </FormField>

        <FormField label="Schedule">
          <select
            className="form-control"
            value={form.schedule_type}
            onChange={(e) => set("schedule_type", e.target.value as ScheduleType)}
          >
            {SCHEDULE_TYPES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </FormField>

        {form.schedule_type === "interval" && (
          <FormField label="Run interval">
            <select
              className="form-control"
              value={form.schedule_interval_minutes}
              onChange={(e) => set("schedule_interval_minutes", e.target.value)}
            >
              <option value="">— Select —</option>
              {INTERVALS.map((i) => (
                <option key={i.value} value={i.value}>
                  {i.label}
                </option>
              ))}
            </select>
          </FormField>
        )}

        {(form.schedule_type === "daily" ||
          form.schedule_type === "weekly" ||
          form.schedule_type === "monthly") && (
          <FormField label="Time of day (UTC)">
            <input
              type="time"
              className="form-control"
              value={form.schedule_time}
              onChange={(e) => set("schedule_time", e.target.value)}
            />
          </FormField>
        )}

        {form.schedule_type === "weekly" && (
          <FormField label="Day of week">
            <select
              className="form-control"
              value={form.schedule_day_of_week}
              onChange={(e) => set("schedule_day_of_week", e.target.value)}
            >
              <option value="">— Select —</option>
              {WEEKDAYS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </FormField>
        )}

        {form.schedule_type === "monthly" && (
          <FormField label="Day of month" help="1–28.">
            <select
              className="form-control"
              value={form.schedule_day_of_month}
              onChange={(e) => set("schedule_day_of_month", e.target.value)}
            >
              <option value="">— Select —</option>
              {Array.from({ length: 28 }, (_, i) => String(i + 1)).map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </FormField>
        )}

        <FormField label="Delivery">
          <select
            className="form-control"
            value={form.delivery_method}
            onChange={(e) => set("delivery_method", e.target.value as DeliveryMethod)}
          >
            {DELIVERY_METHODS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </FormField>

        {form.delivery_method === "email" && (
          <FormField
            label="Email recipients"
            help="One address per line. Recipients receive the report on each scheduled run."
          >
            <textarea
              className="form-control"
              rows={3}
              value={form.email_recipients}
              onChange={(e) => set("email_recipients", e.target.value)}
              placeholder={"one@example.com\ntwo@example.com"}
            />
          </FormField>
        )}

        <CheckboxGroup
          label="Allowed roles"
          help="Roles that can view this report's results (staff always can)."
          options={roleOptions}
          selected={form.allowed_roles}
          onChange={(ids) => set("allowed_roles", ids)}
        />
        <FormCheckbox
          label="Is active"
          checked={form.is_active}
          onChange={(v) => set("is_active", v)}
        />

        <div className="form-actions">
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? "Saving…" : isEdit ? "Save Changes" : "Create Report"}
          </button>
          {isEdit && (
            <button
              type="button"
              className="btn btn-secondary"
              disabled={runPreview.isPending}
              onClick={() => runPreview.mutate()}
            >
              {runPreview.isPending ? "Running…" : "Preview (10 rows)"}
            </button>
          )}
          <Link to="/admin/reports" className="btn btn-ghost">
            Cancel
          </Link>
        </div>
      </form>

      {preview && (
        <div className="card" style={{ marginTop: "var(--md)" }}>
          <ReportResultTable
            report={{ name: form.name, description: "" }}
            execution={preview}
            isPreview
          />
        </div>
      )}
    </div>
  );
}
