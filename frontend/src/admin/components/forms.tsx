import type { ReactNode } from "react";

// Field wrappers matching the legacy management field markup (form-group + label
// + control + .helptext), so the ported CSS styles them.
export function FormField({
	label,
	help,
	htmlFor,
	children,
}: {
	label: string;
	help?: string;
	htmlFor?: string;
	children: ReactNode;
}) {
	return (
		<div className="form-group">
			<label htmlFor={htmlFor}>{label}</label>
			{children}
			{help && <div className="helptext">{help}</div>}
		</div>
	);
}

export function FormCheckbox({
	label,
	checked,
	onChange,
}: {
	label: string;
	checked: boolean;
	onChange: (value: boolean) => void;
}) {
	return (
		<div className="form-group">
			<div className="form-check">
				<label>
					<input
						type="checkbox"
						checked={checked}
						onChange={(event) => onChange(event.target.checked)}
					/>{" "}
					{label}
				</label>
			</div>
		</div>
	);
}

// Rectangular toggle switch, used in place of a checkbox when the field
// deserves its own labelled column (e.g. alongside a FormField) rather than an
// inline "label beside the box".
export function Toggle({
	checked,
	onChange,
}: {
	checked: boolean;
	onChange: (value: boolean) => void;
}) {
	return (
		<label className="toggle-control toggle">
			<input
				type="checkbox"
				checked={checked}
				onChange={(event) => onChange(event.target.checked)}
			/>
			<span className="toggle__track">
				<span className="toggle__thumb" />
			</span>
		</label>
	);
}

// Toggle switch with its own label + explanation beside it, used when the
// field deserves more context than a bare FormField-labelled switch.
export function ToggleField({
	label,
	description,
	checked,
	onChange,
}: {
	label: string;
	description: string;
	checked: boolean;
	onChange: (value: boolean) => void;
}) {
	return (
		<label className="toggle-control toggle-row">
			<input
				type="checkbox"
				checked={checked}
				onChange={(event) => onChange(event.target.checked)}
			/>
			<span className="toggle__track">
				<span className="toggle__thumb" />
			</span>
			<span className="toggle-row__body">
				<span className="toggle-row__label">{label}</span>
				<span className="toggle-row__desc">{description}</span>
			</span>
		</label>
	);
}

// Multi-select checkbox list (matches the legacy `.checkbox-list`), used for the
// role access grants.
export function CheckboxGroup({
	label,
	options,
	selected,
	onChange,
	help,
}: {
	label: string;
	options: { id: string; name: string }[];
	selected: string[];
	onChange: (ids: string[]) => void;
	help?: string;
}) {
	function toggle(id: string) {
		onChange(
			selected.includes(id)
				? selected.filter((x) => x !== id)
				: [...selected, id],
		);
	}
	return (
		<fieldset className="form-group">
			<legend>{label}</legend>
			{options.length === 0 ? (
				<div className="helptext">None available.</div>
			) : (
				<div className="checkbox-list">
					{options.map((o) => (
						<label key={o.id}>
							<input
								type="checkbox"
								checked={selected.includes(o.id)}
								onChange={() => toggle(o.id)}
							/>{" "}
							{o.name}
						</label>
					))}
				</div>
			)}
			{help && <div className="helptext">{help}</div>}
		</fieldset>
	);
}
