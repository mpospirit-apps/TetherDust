import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	type DocSourceInput,
	getDocSource,
	getGenerateOptions,
	updateDocSource,
} from "../../api/docs";
import { CustomSelect, FormField } from "../components/forms";
import { WizardSectionHeading, type WizardStepDef } from "../components/wizard";

interface FormState {
	folder_name: string;
	doc_type: string;
	description: string;
}

const EMPTY: FormState = {
	folder_name: "",
	doc_type: "database",
	description: "",
};

// Identity first, the main classification next.
const STEPS: WizardStepDef[] = [
	{
		key: "identity",
		label: "Identity",
		description: "Review the registered folder and add context for the agent.",
	},
	{
		key: "configuration",
		label: "Configuration",
		description: "Classify what kind of documentation this folder contains.",
	},
];

export function DocSourceFormPage() {
	const { id } = useParams();
	const navigate = useNavigate();
	const queryClient = useQueryClient();

	const [form, setForm] = useState<FormState>(EMPTY);
	const [error, setError] = useState<string | null>(null);

	const options = useQuery({
		queryKey: ["admin", "docsource-options"],
		queryFn: getGenerateOptions,
	});
	const existing = useQuery({
		queryKey: ["admin", "docsources", id],
		queryFn: () => getDocSource(id as string),
	});

	useEffect(() => {
		const s = existing.data;
		if (!s) return;
		setForm({
			folder_name: s.folder_name,
			doc_type: s.doc_type,
			description: s.description,
		});
	}, [existing.data]);

	function set<K extends keyof FormState>(key: K, value: FormState[K]) {
		setForm((f) => ({ ...f, [key]: value }));
	}

	const save = useMutation({
		mutationFn: (payload: DocSourceInput) =>
			updateDocSource(id as string, payload),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["admin", "docsources"] });
			navigate("/admin/docsources");
		},
		onError: (err) => setError(apiErrorDetail(err, "Save failed.")),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);
		const payload: DocSourceInput = {
			doc_type: form.doc_type,
			description: form.description,
		};
		save.mutate(payload);
	}

	const docTypes = options.data?.doc_types ?? [];
	const typeDescription = docTypes.find(
		(t) => t.value === form.doc_type,
	)?.description;

	if (existing.isLoading) {
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
					<h1>Edit {form.folder_name}</h1>
					<p>Map a folder under /sources/docs/ to a typed source</p>
				</div>
				<div className="form-actions">
					<Link to="/admin/docsources" className="btn btn-ghost">
						Cancel
					</Link>
					<button
						type="submit"
						form="docsource-form"
						className="btn btn-primary"
						disabled={save.isPending}
					>
						{save.isPending ? "Saving…" : "Save Changes"}
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

			<form id="docsource-form" onSubmit={onSubmit}>
				<div className="form-split">
					<div className="wizard-section">
						<WizardSectionHeading step={STEPS[0]} index={0} />
						<div className="card">
							<FormField
								label="Documentation Folder"
								help="Folder under /sources/docs/ (chosen at registration)."
							>
								<input
									className="form-control"
									value={form.folder_name}
									disabled
								/>
							</FormField>
							<FormField
								label="Description"
								help="Helps the agent understand what this source contains."
							>
								<textarea
									className="form-control"
									rows={3}
									value={form.description}
									onChange={(e) => set("description", e.target.value)}
								/>
							</FormField>
						</div>
					</div>

					<div className="wizard-section">
						<WizardSectionHeading step={STEPS[1]} index={1} />
						<div className="card">
							<FormField label="Type" help={typeDescription}>
								<CustomSelect
									value={form.doc_type}
									onChange={(v) => set("doc_type", v)}
									options={docTypes}
								/>
							</FormField>
						</div>
					</div>
				</div>
			</form>
		</div>
	);
}
