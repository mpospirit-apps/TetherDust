import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import {
	createDocSource,
	type DocSourceInput,
	getDocSource,
	getDocSourceFolders,
	getGenerateOptions,
	updateDocSource,
} from "../../api/docs";
import { FormCheckbox, FormField } from "../components/forms";

interface FormState {
	folder_name: string;
	doc_type: string;
	description: string;
	file_patterns: string;
	is_active: boolean;
}

const EMPTY: FormState = {
	folder_name: "",
	doc_type: "database",
	description: "",
	file_patterns: "",
	is_active: true,
};

export function DocSourceFormPage() {
	const { id } = useParams();
	const isEdit = Boolean(id);
	const navigate = useNavigate();
	const queryClient = useQueryClient();

	const [form, setForm] = useState<FormState>(EMPTY);
	const [error, setError] = useState<string | null>(null);

	const options = useQuery({
		queryKey: ["admin", "docsource-options"],
		queryFn: getGenerateOptions,
	});
	const folders = useQuery({
		queryKey: ["admin", "docsource-folders"],
		queryFn: getDocSourceFolders,
		enabled: !isEdit,
	});
	const existing = useQuery({
		queryKey: ["admin", "docsources", id],
		queryFn: () => getDocSource(id as string),
		enabled: isEdit,
	});

	useEffect(() => {
		const s = existing.data;
		if (!s) return;
		setForm({
			folder_name: s.folder_name,
			doc_type: s.doc_type,
			description: s.description,
			file_patterns: s.file_patterns?.length
				? JSON.stringify(s.file_patterns)
				: "",
			is_active: s.is_active,
		});
	}, [existing.data]);

	function set<K extends keyof FormState>(key: K, value: FormState[K]) {
		setForm((f) => ({ ...f, [key]: value }));
	}

	const save = useMutation({
		mutationFn: (payload: DocSourceInput) =>
			isEdit
				? updateDocSource(id as string, payload)
				: createDocSource(payload),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["admin", "docsources"] });
			navigate("/admin/docsources");
		},
		onError: (err) => setError(apiErrorDetail(err, "Save failed.")),
	});

	function onSubmit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		setError(null);

		let filePatterns: string[] = [];
		if (form.file_patterns.trim()) {
			try {
				const parsed = JSON.parse(form.file_patterns);
				if (!Array.isArray(parsed)) throw new Error("not array");
				filePatterns = parsed.map(String);
			} catch {
				setError('File patterns must be a JSON array, e.g. ["*.md"].');
				return;
			}
		}

		const payload: DocSourceInput = {
			doc_type: form.doc_type,
			description: form.description,
			file_patterns: filePatterns,
			is_active: form.is_active,
		};
		if (!isEdit) payload.folder_name = form.folder_name;
		save.mutate(payload);
	}

	const docTypes = options.data?.doc_types ?? [];
	const unregistered = (folders.data?.folders ?? []).filter(
		(f) => !f.registered,
	);
	const typeDescription = docTypes.find(
		(t) => t.value === form.doc_type,
	)?.description;

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
					<h1>
						{isEdit
							? `Edit ${form.folder_name}`
							: "Register Documentation Folder"}
					</h1>
					<p>Map a folder under documentations/ to a typed source</p>
				</div>
				<Link
					to={isEdit ? "/admin/docsources" : "/admin/docsources/add"}
					className="btn btn-ghost"
				>
					Back
				</Link>
			</div>

			{error && (
				<div
					className="flash flash-error"
					style={{ marginBottom: "var(--md)" }}
				>
					{error}
				</div>
			)}

			<form onSubmit={onSubmit} className="card" style={{ maxWidth: 640 }}>
				{isEdit ? (
					<FormField label="Documentation Folder">
						<input className="form-control" value={form.folder_name} disabled />
					</FormField>
				) : (
					<FormField
						label="Documentation Folder"
						help="Select a folder from the documentations/ directory."
					>
						<select
							className="form-control"
							value={form.folder_name}
							required
							onChange={(e) => set("folder_name", e.target.value)}
						>
							<option value="">— Select a folder —</option>
							{unregistered.map((f) => (
								<option key={f.name} value={f.name}>
									{f.name}
								</option>
							))}
						</select>
						{unregistered.length === 0 && !folders.isLoading && (
							<div className="helptext">
								No unregistered folders found. Create a folder under
								documentations/ first, or generate one with AI.
							</div>
						)}
					</FormField>
				)}

				<FormField label="Type" help={typeDescription}>
					<select
						className="form-control"
						value={form.doc_type}
						onChange={(e) => set("doc_type", e.target.value)}
					>
						{docTypes.map((t) => (
							<option key={t.value} value={t.value}>
								{t.label}
							</option>
						))}
					</select>
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

				<FormField
					label="File patterns (JSON)"
					help='Glob patterns, e.g. ["*.md"] or ["*.py", "*.sql"]. Leave blank for the default (*.md).'
				>
					<textarea
						className="form-control"
						rows={2}
						style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 13 }}
						placeholder='["*.md"]'
						value={form.file_patterns}
						onChange={(e) => set("file_patterns", e.target.value)}
					/>
				</FormField>

				<FormCheckbox
					label="Is active"
					checked={form.is_active}
					onChange={(v) => set("is_active", v)}
				/>

				<div className="form-actions">
					<button
						type="submit"
						className="btn btn-primary"
						disabled={save.isPending}
					>
						{save.isPending ? "Saving…" : isEdit ? "Save Changes" : "Register"}
					</button>
					<Link to="/admin/docsources" className="btn btn-secondary">
						Cancel
					</Link>
				</div>
			</form>
		</div>
	);
}
