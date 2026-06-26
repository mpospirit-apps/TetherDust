import { type ReactNode } from "react";

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
        <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
        <label>{label}</label>
      </div>
    </div>
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
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  }
  return (
    <div className="form-group">
      <label>{label}</label>
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
    </div>
  );
}
