import {
	type ChangeEvent,
	type KeyboardEvent,
	type ReactNode,
	useEffect,
	useRef,
	useState,
} from "react";

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

export interface SelectOption {
	value: string;
	label: string;
}

// Styled replacement for a native <select> (see .custom-select in forms.css),
// matching the app's look instead of the browser's default popup. Focus stays
// on the trigger the whole time — arrow keys move `.is-focused` through the
// options and Enter picks one — so there's no extra tabindex/focus juggling
// on the option list itself.
export function CustomSelect({
	value,
	onChange,
	options,
	placeholder = "— Select —",
}: {
	value: string;
	onChange: (value: string) => void;
	options: SelectOption[];
	placeholder?: string;
}) {
	const [open, setOpen] = useState(false);
	const [focusedIndex, setFocusedIndex] = useState(-1);
	const rootRef = useRef<HTMLDivElement>(null);

	const selectedIndex = options.findIndex((o) => o.value === value);
	const selected = options[selectedIndex];

	useEffect(() => {
		if (!open) return;
		function onDocMouseDown(event: MouseEvent) {
			if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
		}
		document.addEventListener("mousedown", onDocMouseDown);
		return () => document.removeEventListener("mousedown", onDocMouseDown);
	}, [open]);

	function openMenu() {
		setFocusedIndex(selectedIndex >= 0 ? selectedIndex : 0);
		setOpen(true);
	}

	function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
		if (!open) {
			if (
				event.key === "ArrowDown" ||
				event.key === "Enter" ||
				event.key === " "
			) {
				event.preventDefault();
				openMenu();
			}
			return;
		}
		if (event.key === "ArrowDown") {
			event.preventDefault();
			setFocusedIndex((i) => Math.min(i + 1, options.length - 1));
		} else if (event.key === "ArrowUp") {
			event.preventDefault();
			setFocusedIndex((i) => Math.max(i - 1, 0));
		} else if (event.key === "Enter" || event.key === " ") {
			event.preventDefault();
			const option = options[focusedIndex];
			if (option) {
				onChange(option.value);
				setOpen(false);
			}
		} else if (event.key === "Escape") {
			event.preventDefault();
			setOpen(false);
		}
	}

	return (
		<div className={`custom-select${open ? " is-open" : ""}`} ref={rootRef}>
			<button
				type="button"
				className="custom-select__trigger"
				aria-haspopup="listbox"
				aria-expanded={open}
				onClick={() => (open ? setOpen(false) : openMenu())}
				onKeyDown={onTriggerKeyDown}
			>
				<span>{selected?.label ?? placeholder}</span>
				<i className="fa-solid fa-chevron-down" />
			</button>
			{open && (
				<div className="custom-select__dropdown" role="listbox">
					{options.map((option, index) => (
						<button
							key={option.value}
							type="button"
							tabIndex={-1}
							role="option"
							aria-selected={option.value === value}
							className={`custom-select__option${
								option.value === value ? " is-selected" : ""
							}${index === focusedIndex ? " is-focused" : ""}`}
							onMouseEnter={() => setFocusedIndex(index)}
							onClick={() => {
								onChange(option.value);
								setOpen(false);
							}}
						>
							{option.label}
						</button>
					))}
				</div>
			)}
		</div>
	);
}

// Styled replacement for a text <input> + native <datalist> (see .combo-input
// in docsgen.css), matching the app's look instead of the browser's default
// autocomplete popup. Unlike CustomSelect this stays a free-text field — any
// value can be typed and submitted, the dropdown is just suggestions plus a
// "Create …" entry when the typed value doesn't match one of them.
export function ComboInput({
	value,
	onChange,
	options,
	placeholder,
	required,
}: {
	value: string;
	onChange: (value: string) => void;
	options: string[];
	placeholder?: string;
	required?: boolean;
}) {
	const [open, setOpen] = useState(false);
	const [focusedIndex, setFocusedIndex] = useState(-1);
	const rootRef = useRef<HTMLDivElement>(null);

	const trimmed = value.trim();
	const filtered = trimmed
		? options.filter((o) => o.toLowerCase().includes(trimmed.toLowerCase()))
		: options;
	const exactMatch = options.some(
		(o) => o.toLowerCase() === trimmed.toLowerCase(),
	);
	const showCreate = trimmed !== "" && !exactMatch;
	const itemCount = filtered.length + (showCreate ? 1 : 0);

	useEffect(() => {
		if (!open) return;
		function onDocMouseDown(event: MouseEvent) {
			if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
		}
		document.addEventListener("mousedown", onDocMouseDown);
		return () => document.removeEventListener("mousedown", onDocMouseDown);
	}, [open]);

	function selectIndex(index: number) {
		if (index < filtered.length) {
			onChange(filtered[index]);
		} else if (showCreate) {
			onChange(trimmed);
		}
		setOpen(false);
		setFocusedIndex(-1);
	}

	function onInputChange(event: ChangeEvent<HTMLInputElement>) {
		onChange(event.target.value);
		setFocusedIndex(-1);
		setOpen(true);
	}

	function onInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
		if (event.key === "ArrowDown") {
			event.preventDefault();
			if (!open) {
				setOpen(true);
				return;
			}
			setFocusedIndex((i) => Math.min(i + 1, itemCount - 1));
		} else if (event.key === "ArrowUp") {
			event.preventDefault();
			setFocusedIndex((i) => Math.max(i - 1, 0));
		} else if (event.key === "Enter") {
			if (open && focusedIndex >= 0) {
				event.preventDefault();
				selectIndex(focusedIndex);
			}
		} else if (event.key === "Escape") {
			setOpen(false);
		}
	}

	return (
		<div className={`combo-input${open ? " is-open" : ""}`} ref={rootRef}>
			<input
				className="form-control"
				value={value}
				required={required}
				placeholder={placeholder}
				onChange={onInputChange}
				onFocus={() => setOpen(true)}
				onKeyDown={onInputKeyDown}
			/>
			{open && (
				<div className="combo-input__dropdown">
					{filtered.length === 0 && !showCreate && (
						<div className="combo-input__empty">No suggestions yet.</div>
					)}
					{filtered.map((option, index) => (
						<button
							key={option}
							type="button"
							tabIndex={-1}
							className={`combo-input__item${
								option === value ? " is-selected" : ""
							}${index === focusedIndex ? " is-focused" : ""}`}
							onMouseEnter={() => setFocusedIndex(index)}
							onClick={() => selectIndex(index)}
						>
							{option}
						</button>
					))}
					{showCreate && (
						<button
							type="button"
							tabIndex={-1}
							className={`combo-input__item combo-input__item--create${
								filtered.length === focusedIndex ? " is-focused" : ""
							}`}
							onMouseEnter={() => setFocusedIndex(filtered.length)}
							onClick={() => selectIndex(filtered.length)}
						>
							Create "{trimmed}"
						</button>
					)}
				</div>
			)}
		</div>
	);
}
