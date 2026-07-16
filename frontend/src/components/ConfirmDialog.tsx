import { useEffect } from "react";
import { createPortal } from "react-dom";

interface ConfirmDialogProps {
	title: string;
	message: React.ReactNode;
	confirmLabel?: string;
	cancelLabel?: string;
	onConfirm: () => void;
	onCancel: () => void;
}

// Generic replacement for window.confirm(), styled to match the rest of the
// app (see .confirm-modal in layouts.css) instead of the native browser
// dialog. Only mount this when the dialog should be open (e.g. guard the
// call site on a nullable "pending" value) — there's nothing to render when
// closed.
export function ConfirmDialog({
	title,
	message,
	confirmLabel = "Delete",
	cancelLabel = "Cancel",
	onConfirm,
	onCancel,
}: ConfirmDialogProps) {
	useEffect(() => {
		function onKeyDown(event: KeyboardEvent) {
			if (event.key === "Escape") onCancel();
		}
		document.addEventListener("keydown", onKeyDown);
		return () => document.removeEventListener("keydown", onKeyDown);
	}, [onCancel]);

	return createPortal(
		<div className="confirm-modal is-open">
			<button
				type="button"
				className="confirm-modal__backdrop"
				aria-label="Close dialog"
				onClick={onCancel}
			/>
			<div className="confirm-modal__panel" role="dialog" aria-modal="true">
				<div className="confirm-modal__header">
					<i className="fa-solid fa-triangle-exclamation" />
					<h2>{title}</h2>
				</div>
				<div className="confirm-modal__body">{message}</div>
				<div className="confirm-modal__footer">
					<button type="button" className="btn btn-ghost" onClick={onCancel}>
						{cancelLabel}
					</button>
					<button type="button" className="btn btn-danger" onClick={onConfirm}>
						{confirmLabel}
					</button>
				</div>
			</div>
		</div>,
		document.body,
	);
}
