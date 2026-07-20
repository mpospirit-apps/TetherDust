import { useEffect } from "react";
import { createPortal } from "react-dom";

interface AlertDialogProps {
	title: string;
	message: React.ReactNode;
	closeLabel?: string;
	onClose: () => void;
}

// Generic replacement for window.alert(), styled to match ConfirmDialog (see
// .confirm-modal in layouts.css) instead of the native browser dialog. Only
// mount this when the dialog should be open (e.g. guard the call site on a
// nullable "message" value) — there's nothing to render when closed.
export function AlertDialog({
	title,
	message,
	closeLabel = "OK",
	onClose,
}: AlertDialogProps) {
	useEffect(() => {
		function onKeyDown(event: KeyboardEvent) {
			if (event.key === "Escape") onClose();
		}
		document.addEventListener("keydown", onKeyDown);
		return () => document.removeEventListener("keydown", onKeyDown);
	}, [onClose]);

	return createPortal(
		<div className="confirm-modal is-open">
			<button
				type="button"
				className="confirm-modal__backdrop"
				aria-label="Close dialog"
				onClick={onClose}
			/>
			<div className="confirm-modal__panel" role="dialog" aria-modal="true">
				<div className="confirm-modal__header">
					<i className="fa-solid fa-triangle-exclamation" />
					<h2>{title}</h2>
				</div>
				<div className="confirm-modal__body">{message}</div>
				<div className="confirm-modal__footer">
					<button type="button" className="btn btn-primary" onClick={onClose}>
						{closeLabel}
					</button>
				</div>
			</div>
		</div>,
		document.body,
	);
}
