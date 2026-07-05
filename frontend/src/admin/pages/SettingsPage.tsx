import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import {
	type GeneralSettings,
	getGeneralSettings,
	getSmtpSettings,
	type SmtpSettingsInput,
	testSmtp,
	updateGeneralSettings,
	updateSmtpSettings,
} from "../../api/admin";
import { ApiError, apiErrorDetail } from "../../api/client";
import { FormCheckbox, FormField } from "../components/forms";

function numOrNull(value: string): number | null {
	return value.trim() === "" ? null : Number(value);
}

function smtpErrorText(err: unknown): string {
	if (
		err instanceof ApiError &&
		err.data &&
		typeof err.data === "object" &&
		"error" in err.data
	) {
		return String((err.data as Record<string, unknown>).error);
	}
	return "Test failed.";
}

interface GeneralForm {
	codex_service_url: string;
	mcp_base_url: string;
	docgen_timeout: string;
	doclibgen_timeout: string;
	chartgen_timeout: string;
	max_row_limit: string;
	hot_reload_interval: string;
}

const EMPTY_GENERAL: GeneralForm = {
	codex_service_url: "",
	mcp_base_url: "",
	docgen_timeout: "",
	doclibgen_timeout: "",
	chartgen_timeout: "",
	max_row_limit: "",
	hot_reload_interval: "",
};

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

export function SettingsPage() {
	const queryClient = useQueryClient();
	const general = useQuery({
		queryKey: ["admin", "settings", "general"],
		queryFn: getGeneralSettings,
	});
	const smtp = useQuery({
		queryKey: ["admin", "settings", "smtp"],
		queryFn: getSmtpSettings,
	});

	const [generalForm, setGeneralForm] = useState<GeneralForm>(EMPTY_GENERAL);
	const [smtpForm, setSmtpForm] = useState<SmtpForm>(EMPTY_SMTP);
	const [hasPassword, setHasPassword] = useState(false);
	const [generalError, setGeneralError] = useState<string | null>(null);
	const [smtpError, setSmtpError] = useState<string | null>(null);
	const [saved, setSaved] = useState(false);
	const [testMsg, setTestMsg] = useState<{ ok: boolean; text: string } | null>(
		null,
	);

	useEffect(() => {
		const d = general.data;
		if (!d) return;
		setGeneralForm({
			codex_service_url: d.codex_service_url ?? "",
			mcp_base_url: d.mcp_base_url ?? "",
			docgen_timeout: d.docgen_timeout == null ? "" : String(d.docgen_timeout),
			doclibgen_timeout:
				d.doclibgen_timeout == null ? "" : String(d.doclibgen_timeout),
			chartgen_timeout:
				d.chartgen_timeout == null ? "" : String(d.chartgen_timeout),
			max_row_limit: d.max_row_limit == null ? "" : String(d.max_row_limit),
			hot_reload_interval:
				d.hot_reload_interval == null ? "" : String(d.hot_reload_interval),
		});
	}, [general.data]);

	useEffect(() => {
		const d = smtp.data;
		if (!d) return;
		setSmtpForm({
			smtp_host: d.smtp_host ?? "",
			smtp_port: d.smtp_port == null ? "" : String(d.smtp_port),
			smtp_username: d.smtp_username ?? "",
			smtp_password: "",
			smtp_use_tls: d.smtp_use_tls,
			smtp_from_email: d.smtp_from_email ?? "",
			email_max_rows: d.email_max_rows == null ? "" : String(d.email_max_rows),
		});
		setHasPassword(d.has_password);
	}, [smtp.data]);

	function setGeneral<K extends keyof GeneralForm>(key: K, value: string) {
		setGeneralForm((f) => ({ ...f, [key]: value }));
	}
	function setSmtp<K extends keyof SmtpForm>(key: K, value: SmtpForm[K]) {
		setSmtpForm((f) => ({ ...f, [key]: value }));
	}

	const save = useMutation({
		mutationFn: async () => {
			setGeneralError(null);
			setSmtpError(null);
			const generalPayload: GeneralSettings = {
				codex_service_url: generalForm.codex_service_url,
				mcp_base_url: generalForm.mcp_base_url,
				docgen_timeout: numOrNull(generalForm.docgen_timeout),
				doclibgen_timeout: numOrNull(generalForm.doclibgen_timeout),
				chartgen_timeout: numOrNull(generalForm.chartgen_timeout),
				max_row_limit: numOrNull(generalForm.max_row_limit),
				hot_reload_interval: numOrNull(generalForm.hot_reload_interval),
			};
			const smtpPayload: SmtpSettingsInput = {
				smtp_host: smtpForm.smtp_host,
				smtp_port: numOrNull(smtpForm.smtp_port),
				smtp_username: smtpForm.smtp_username,
				smtp_use_tls: smtpForm.smtp_use_tls,
				smtp_from_email: smtpForm.smtp_from_email,
				email_max_rows: numOrNull(smtpForm.email_max_rows),
				...(smtpForm.smtp_password
					? { smtp_password: smtpForm.smtp_password }
					: {}),
			};
			const [generalResult, smtpResult] = await Promise.allSettled([
				updateGeneralSettings(generalPayload),
				updateSmtpSettings(smtpPayload),
			]);
			let hasError = false;
			if (generalResult.status === "rejected") {
				setGeneralError(apiErrorDetail(generalResult.reason, "Save failed."));
				hasError = true;
			}
			if (smtpResult.status === "rejected") {
				setSmtpError(apiErrorDetail(smtpResult.reason, "Save failed."));
				hasError = true;
			}
			if (hasError) throw new Error("Settings save failed");
		},
		onSuccess: () => {
			setSaved(true);
			queryClient.invalidateQueries({ queryKey: ["admin", "settings"] });
			setTimeout(() => setSaved(false), 2500);
		},
	});

	const test = useMutation({
		mutationFn: testSmtp,
		onSuccess: (r) => setTestMsg({ ok: true, text: r.message ?? "Sent." }),
		onError: (err) => setTestMsg({ ok: false, text: smtpErrorText(err) }),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		save.mutate();
	}

	const loading = general.isLoading || smtp.isLoading;

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Settings</h1>
					<p>General operational settings and email (SMTP) configuration.</p>
				</div>
				<div className="form-actions">
					{saved && <span className="badge badge-success">Saved ✓</span>}
					<button
						type="submit"
						form="settings-form"
						className="btn btn-primary"
						disabled={save.isPending || loading}
					>
						{save.isPending ? "Saving…" : "Save Settings"}
					</button>
				</div>
			</div>

			{loading ? (
				<div className="card">
					<p className="text-sec">Loading…</p>
				</div>
			) : (
				<form id="settings-form" onSubmit={onSubmit}>
					<div className="form-split">
						<div className="card">
							<h3 style={{ margin: "0 0 var(--md)" }}>General</h3>
							{generalError && (
								<div
									className="flash flash-error"
									style={{ marginBottom: "var(--md)" }}
								>
									{generalError}
								</div>
							)}
							<FormField label="Codex Service URL">
								<input
									className="form-control"
									value={generalForm.codex_service_url}
									onChange={(e) =>
										setGeneral("codex_service_url", e.target.value)
									}
								/>
							</FormField>
							<FormField label="MCP Base URL">
								<input
									className="form-control"
									value={generalForm.mcp_base_url}
									onChange={(e) => setGeneral("mcp_base_url", e.target.value)}
								/>
							</FormField>
							<div className="form-grid">
								<FormField label="Doc Gen Timeout (s)">
									<input
										className="form-control"
										type="number"
										value={generalForm.docgen_timeout}
										onChange={(e) =>
											setGeneral("docgen_timeout", e.target.value)
										}
									/>
								</FormField>
								<FormField label="Doc Library Gen Timeout (s)">
									<input
										className="form-control"
										type="number"
										value={generalForm.doclibgen_timeout}
										onChange={(e) =>
											setGeneral("doclibgen_timeout", e.target.value)
										}
									/>
								</FormField>
							</div>
							<div className="form-grid">
								<FormField label="Chart Gen Timeout (s)">
									<input
										className="form-control"
										type="number"
										value={generalForm.chartgen_timeout}
										onChange={(e) =>
											setGeneral("chartgen_timeout", e.target.value)
										}
									/>
								</FormField>
								<FormField label="Max Row Limit" help="Blank = no limit.">
									<input
										className="form-control"
										type="number"
										value={generalForm.max_row_limit}
										onChange={(e) =>
											setGeneral("max_row_limit", e.target.value)
										}
									/>
								</FormField>
							</div>
							<FormField
								label="Hot Reload Interval (s)"
								help="Blank to disable."
							>
								<input
									className="form-control"
									type="number"
									value={generalForm.hot_reload_interval}
									onChange={(e) =>
										setGeneral("hot_reload_interval", e.target.value)
									}
								/>
							</FormField>
						</div>

						<div className="card">
							<h3 style={{ margin: "0 0 var(--md)" }}>Email (SMTP)</h3>
							{smtpError && (
								<div
									className="flash flash-error"
									style={{ marginBottom: "var(--md)" }}
								>
									{smtpError}
								</div>
							)}
							<div className="form-grid">
								<FormField label="SMTP Host">
									<input
										className="form-control"
										value={smtpForm.smtp_host}
										onChange={(e) => setSmtp("smtp_host", e.target.value)}
									/>
								</FormField>
								<FormField label="SMTP Port">
									<input
										className="form-control"
										type="number"
										value={smtpForm.smtp_port}
										onChange={(e) => setSmtp("smtp_port", e.target.value)}
									/>
								</FormField>
							</div>
							<div className="form-grid">
								<FormField label="Username">
									<input
										className="form-control"
										autoComplete="off"
										value={smtpForm.smtp_username}
										onChange={(e) => setSmtp("smtp_username", e.target.value)}
									/>
								</FormField>
								<FormField
									label="Password"
									help={
										hasPassword ? "Leave blank to keep existing." : undefined
									}
								>
									<input
										className="form-control"
										type="password"
										autoComplete="new-password"
										placeholder={
											hasPassword
												? "••••••••  (leave blank to keep)"
												: "SMTP password"
										}
										value={smtpForm.smtp_password}
										onChange={(e) => setSmtp("smtp_password", e.target.value)}
									/>
								</FormField>
							</div>
							<FormField label="From Email">
								<input
									className="form-control"
									type="email"
									value={smtpForm.smtp_from_email}
									onChange={(e) => setSmtp("smtp_from_email", e.target.value)}
								/>
							</FormField>
							<FormField label="Max Rows in CSV Attachment">
								<input
									className="form-control"
									type="number"
									value={smtpForm.email_max_rows}
									onChange={(e) => setSmtp("email_max_rows", e.target.value)}
								/>
							</FormField>
							<FormCheckbox
								label="Use TLS"
								checked={smtpForm.smtp_use_tls}
								onChange={(v) => setSmtp("smtp_use_tls", v)}
							/>
							<div
								className="form-actions"
								style={{ marginTop: "var(--md)", flexWrap: "wrap" }}
							>
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
								{testMsg && (
									<span
										className={
											testMsg.ok ? "badge badge-success" : "badge badge-error"
										}
									>
										{testMsg.text}
									</span>
								)}
							</div>
						</div>
					</div>
				</form>
			)}
		</div>
	);
}
