// Pure constants and tiny SVG/string helpers shared across the tether canvas.
// Ported from the legacy tethers/constants.js.

export const REL_COLOR: Record<string, string> = {
	reads: "var(--c-cyan)",
	writes: "var(--c-pink)",
	references: "var(--c-lime)",
	"maps-to": "var(--c-orange)",
};

export const KIND_LABEL: Record<string, string> = {
	"code-file": "File",
	"code-symbol": "Symbol",
	"db-table": "Table",
	"db-column": "Column",
};

export const KIND_ICON: Record<string, string> = {
	"code-file": "fa-file-lines",
	"db-table": "fa-table",
};

export const ALL_RELS = ["reads", "writes", "references", "maps-to"];

export const ROW_HEIGHT = 26;
export const HEADER_HEIGHT = 36;
export const CARD_PADDING_Y = 8;
export const MAX_INLINE_ROWS = 8;
export const PREVIEW_ROWS = 5;
export const MIN_CARD_W = 220;
export const MAX_CARD_W = 360;

export const DEFAULT_SPREAD = 1500;
export const SPREAD_KEY = "tether:spread";

export function getSpread(): number {
	const stored = Number(localStorage.getItem(SPREAD_KEY));
	return Number.isFinite(stored) && stored > 0 ? stored : DEFAULT_SPREAD;
}

export const DEFAULT_GAP = 0.3;
export const GAP_KEY = "tether:gap";

export function getGap(): number {
	const stored = Number(localStorage.getItem(GAP_KEY));
	return Number.isFinite(stored) && stored > 0 ? stored : DEFAULT_GAP;
}

export function svgEl(tag: string, attrs?: Record<string, string>): SVGElement {
	const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
	if (attrs) for (const k of Object.keys(attrs)) el.setAttribute(k, attrs[k]);
	return el;
}

export function cssEscape(s: string): string {
	return window.CSS && CSS.escape
		? CSS.escape(s)
		: String(s).replace(/(["\\])/g, "\\$1");
}

export function escapeHtml(s: string): string {
	return String(s).replace(
		/[&<>"']/g,
		(c) =>
			({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
				c
			] as string,
	);
}
