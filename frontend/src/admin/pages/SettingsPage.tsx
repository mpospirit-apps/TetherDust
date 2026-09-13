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
import { FormField, ToggleInline } from "../components/forms";

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
	docgen_timeout: string;
	doclibgen_timeout: string;
	chartgen_timeout: string;
}

const EMPTY_GENERAL: GeneralForm = {
	docgen_timeout: "",
	doclibgen_timeout: "",
	chartgen_timeout: "",
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
			docgen_timeout: d.docgen_timeout == null ? "" : String(d.docgen_timeout),
			doclibgen_timeout:
				d.doclibgen_timeout == null ? "" : String(d.doclibgen_timeout),
			chartgen_timeout:
				d.chartgen_timeout == null ? "" : String(d.chartgen_timeout),
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
				docgen_timeout: numOrNull(generalForm.docgen_timeout),
				doclibgen_timeout: numOrNull(generalForm.doclibgen_timeout),
				chartgen_timeout: numOrNull(generalForm.chartgen_timeout),
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
					<p>Agent generation timeouts and email (SMTP) configuration.</p>
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
							<h3 style={{ margin: "0 0 var(--xs)" }}>Timeouts</h3>
							<p
								className="text-sec"
								style={{ margin: "0 0 var(--md)", fontSize: "13px" }}
							>
								How long the AI agent may work on one background generation job
								before it is cut off and the run is marked failed in its
								generation log. Raise a timeout if long runs keep failing part
								way; lower it to stop a stuck agent holding a worker.
							</p>
							{generalError && (
								<div
									className="flash flash-error"
									style={{ marginBottom: "var(--md)" }}
								>
									{generalError}
								</div>
							)}
							<div className="form-grid">
								<FormField
									label="Doc Gen Timeout (s)"
									help="One document — a single table or file. Default 1800 (30 min)."
								>
									<input
										className="form-control"
										type="number"
										value={generalForm.docgen_timeout}
										onChange={(e) =>
											setGeneral("docgen_timeout", e.target.value)
										}
									/>
								</FormField>
								<FormField
									label="Doc Library Gen Timeout (s)"
									help="A whole library in one run, so it needs longer than a single document. Default 3600 (1 hr)."
								>
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
							<FormField
								label="Chart Gen Timeout (s)"
								help="One dashboard chart, from prompt to saved spec. Default 1800 (30 min)."
							>
								<input
									className="form-control"
									type="number"
									value={generalForm.chartgen_timeout}
									onChange={(e) =>
										setGeneral("chartgen_timeout", e.target.value)
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
							<div className="control-row">
								<ToggleInline
									label="Use TLS"
									checked={smtpForm.smtp_use_tls}
									onChange={(v) => setSmtp("smtp_use_tls", v)}
								/>
								<button
									type="button"
									className="btn btn-secondary"
									disabled={test.isPending}
									onClick={() => {
										setTestMsg(null);
										test.mutate();
									}}
								>
									{test.isPending ? (
										<>
											<i className="fa-solid fa-spinner fa-spin" /> Sending…
										</>
									) : (
										<>
											<i className="fa-solid fa-paper-plane" /> Send Test Email
										</>
									)}
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
