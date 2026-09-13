// Type metrics for names painted onto surfaces.
//
// Every label in the city is monospace, which is what makes this arithmetic
// rather than measurement: no text node has to be laid out and queried to know
// how wide it will be, so the packer can size a building from its own name
// before anything is drawn.

import { ISO_X } from "./iso";

/** advance width of one monospace glyph, as a fraction of the font size */
export const MONO_ADV = 0.62;

/** width of a string at a given font size, in px */
export const textPx = (s: string, font: number): number =>
	s.length * MONO_ADV * font;

/** the same width in world units, for sizing a footprint from its label */
export const textWorld = (s: string, font: number): number =>
	textPx(s, font) / ISO_X;

/**
 * Middle-trim, because an identifier carries meaning at both ends:
 * `chart_generation_log` cut from the right is `chart_gene…`, which could be
 * anything, while cut from the middle it is `chart_…_log`.
 */
export function trimMid(s: string, maxChars: number): string {
	if (maxChars >= s.length) return s;
	if (maxChars <= 1) return "…";
	const keep = maxChars - 1;
	const head = Math.ceil(keep / 2);
	const tail = keep - head;
	return `${s.slice(0, head)}…${tail ? s.slice(-tail) : ""}`;
}

// ── wrapping a name around a drum ────────────────────────────────────────────
//
// A glyph sitting φ round from the camera-facing line lands at screen
// (rx·sin φ, ry·cos φ) off the disk's axis and is squashed by cos φ — so the run
// compresses and the baseline bows exactly as a label wrapped on a can does.
// Advance is uniform in arc length, i.e. uniform in φ, which is what keeps the
// spacing honest.

/** wrap limit in radians either side of the camera-facing line */
export const PHI_MAX = 1.28;

/** one local unit of arc runs 1/ISO_X world units around the side */
export const capLocal = (drawnR: number): number =>
	drawnR * ISO_X * Math.SQRT1_2;

/** how many px of readable run a drum offers before the wrap tips too far */
export const sideRoom = (drawnR: number): number =>
	2 * PHI_MAX * capLocal(drawnR);

export interface Glyph {
	ch: string;
	x: number;
	y: number;
	/** horizontal squash, from the angle it sits at */
	scale: number;
}

/**
 * Place one storey's name around a drum. Static in the disk's own frame — a
 * ground circle projects to the same ellipse at every bearing, so these never
 * move relative to their drum and the layout only has to place the drum.
 */
export function wrapGlyphs(
	text: string,
	drawnR: number,
	font: number,
	rx: number,
	ry: number,
	y0: number,
): Glyph[] {
	const adv = MONO_ADV * font;
	const phiPer = 1 / capLocal(drawnR);
	const out: Glyph[] = [];
	const chars = [...text];
	chars.forEach((ch, i) => {
		const phi = (i - (chars.length - 1) / 2) * adv * phiPer;
		const c = Math.cos(phi);
		out.push({ ch, x: rx * Math.sin(phi), y: y0 + ry * c, scale: c });
	});
	return out;
}
