import {
	cloneElement,
	type ReactElement,
	type SyntheticEvent,
	useState,
} from "react";
import { createPortal } from "react-dom";

interface TooltipPos {
	top: number;
	left: number;
}

interface TriggerProps {
	onMouseEnter: (event: SyntheticEvent) => void;
	onMouseLeave: () => void;
	onFocus: (event: SyntheticEvent) => void;
	onBlur: () => void;
}

// Portaled to <body> so the tooltip escapes ancestors with `overflow: auto`
// (e.g. the admin tables' horizontal-scroll wrapper), which would otherwise
// clip anything positioned above the trigger. Handlers attach directly to
// the child (rather than a wrapping span) so the trigger stays the real
// interactive element — and focus shows the tooltip too, for keyboard users.
export function ActionTooltip({
	content,
	children,
}: {
	content: string;
	children: ReactElement<Partial<TriggerProps>>;
}) {
	const [pos, setPos] = useState<TooltipPos | null>(null);

	function show(event: SyntheticEvent) {
		const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
		setPos({ top: rect.top - 8, left: rect.left + rect.width / 2 });
	}

	function hide() {
		setPos(null);
	}

	return (
		<>
			{cloneElement(children, {
				onMouseEnter: show,
				onMouseLeave: hide,
				onFocus: show,
				onBlur: hide,
			} satisfies Partial<TriggerProps>)}
			{pos &&
				createPortal(
					<span
						className="action-tooltip"
						style={{ top: pos.top, left: pos.left }}
					>
						{content}
					</span>,
					document.body,
				)}
		</>
	);
}
