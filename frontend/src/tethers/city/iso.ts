// 2:1 dimetric projection. One world unit is TILE px across and TILE/2 down; z
// is screen-vertical only, which keeps the projection affine and cheap.
//
// Rotation happens in the ground plane *before* projection, so the camera stays
// a fixed dimetric and only the world turns. Nothing here may assume an
// axis-aligned footprint: the quarter turns are rest stops, not the only states.
//
// The bearing is passed explicitly rather than held at module scope. Two scenes
// can exist at once — React's StrictMode mounts every effect twice in dev — and
// shared mutable camera state would have them fighting over it.

export type Pt = [number, number];
export type Pt3 = [number, number, number];

export const TILE = 30;
export const ISO_X = TILE;
export const ISO_Y = TILE / 2;
export const Z_UNIT = 13;

// Solving P(v) = 0 gives the camera's null direction v = (1, 1, 2·ISO_Y/Z_UNIT):
// every world point sharing a pixel lies on p + s·v, and +v points at the
// camera. That single fact is what occlusion and routing are both built on.
export const ZK = (2 * ISO_Y) / Z_UNIT;

export const px = (x: number, y: number): number => (x - y) * ISO_X;
export const py = (x: number, y: number, z = 0): number =>
	(x + y) * ISO_Y - z * Z_UNIT;
export const P = (x: number, y: number, z = 0): Pt => [px(x, y), py(x, y, z)];

export const n1 = (v: number): string => v.toFixed(1);
export const poly = (pts: Pt[]): string =>
	pts.map((p) => `${n1(p[0])},${n1(p[1])}`).join(" ");

// ── bearing ──────────────────────────────────────────────────────────────────

export interface Bearing {
	readonly theta: number;
	readonly sin: number;
	readonly cos: number;
	/** rotation centre, in unrotated world coordinates */
	readonly cx: number;
	readonly cy: number;
	/** the camera ray (1, 1) rotated back out of world space */
	readonly rx: number;
	readonly ry: number;
}

export function bearing(theta: number, cx: number, cy: number): Bearing {
	const sin = Math.sin(theta);
	const cos = Math.cos(theta);
	return { theta, sin, cos, cx, cy, rx: cos - sin, ry: sin + cos };
}

/** world → rotated world */
export function rotPt(bg: Bearing, x: number, y: number): Pt {
	const dx = x - bg.cx;
	const dy = y - bg.cy;
	return [bg.cx + dx * bg.cos + dy * bg.sin, bg.cy - dx * bg.sin + dy * bg.cos];
}

/** rotated world → world, so a footprint can be tested where it was authored */
export function unrotPt(bg: Bearing, x: number, y: number): Pt {
	const dx = x - bg.cx;
	const dy = y - bg.cy;
	return [bg.cx + dx * bg.cos - dy * bg.sin, bg.cy + dx * bg.sin + dy * bg.cos];
}

export function cornersOf(
	bg: Bearing,
	x: number,
	y: number,
	w: number,
	d: number,
): Pt[] {
	return [
		[x, y],
		[x + w, y],
		[x + w, y + d],
		[x, y + d],
	].map((c) => rotPt(bg, c[0], c[1]));
}

// ── surfaces ─────────────────────────────────────────────────────────────────

export interface Wall {
	a: Pt;
	b: Pt;
	nx: number;
	ny: number;
	/** > 0 when the wall's normal points down-screen, i.e. towards the camera */
	facing: number;
	shade: number;
}

// Light direction on the ground plane. A wall's shade comes from its own normal,
// so facades re-shade as the city turns rather than being fixed to a face.
const LX = -0.41;
const LY = 0.91;

export function walls(cs: Pt[]): Wall[] {
	const out: Wall[] = [];
	for (let i = 0; i < 4; i++) {
		const a = cs[i];
		const b = cs[(i + 1) % 4];
		const ex = b[0] - a[0];
		const ey = b[1] - a[1];
		const L = Math.hypot(ex, ey) || 1;
		const nx = ey / L;
		const ny = -ex / L;
		out.push({ a, b, nx, ny, facing: nx + ny, shade: nx * LX + ny * LY });
	}
	return out;
}

export const shadeClass = (v: number): string =>
	v > 0.35 ? "sh-hi" : v < -0.35 ? "sh-lo" : "sh-mid";

/** the wall of a drum between two heights: front rim, two verticals, back rim */
export function cylinder(cw: Pt, r: number, z0: number, z1: number): string {
	const a = P(cw[0], cw[1], z0);
	const b = P(cw[0], cw[1], z1);
	const rx = r * ISO_X;
	const ry = r * ISO_Y;
	return (
		`M${n1(b[0] - rx)},${n1(b[1])}L${n1(a[0] - rx)},${n1(a[1])}` +
		`A${n1(rx)},${n1(ry)} 0 0 0 ${n1(a[0] + rx)},${n1(a[1])}` +
		`L${n1(b[0] + rx)},${n1(b[1])}` +
		`A${n1(rx)},${n1(ry)} 0 0 1 ${n1(b[0] - rx)},${n1(b[1])}Z`
	);
}

/** the visible front half of a rim — the seam between two stacked disks */
export function seam(cw: Pt, r: number, z: number): string {
	const a = P(cw[0], cw[1], z);
	const rx = r * ISO_X;
	const ry = r * ISO_Y;
	return (
		`M${n1(a[0] - rx)},${n1(a[1])}` +
		`A${n1(rx)},${n1(ry)} 0 0 0 ${n1(a[0] + rx)},${n1(a[1])}`
	);
}

// The roof plane written as a text basis. Under the projection
//
//     unrot +x → rotated (cos, -sin) → screen ((cos+sin)·ISO_X, (cos-sin)·ISO_Y)
//     unrot +y → rotated (sin,  cos) → screen ((sin-cos)·ISO_X, (sin+cos)·ISO_Y)
//
// so a matrix built from those two columns lays a <text> flat on the roof,
// sheared exactly as the roof is, with one local unit = 1/ISO_X world units —
// which is why a glyph advance reads at roughly its nominal pixel width. The
// determinant is exactly 1, so painted text shears but never changes area.
// Flipping the whole basis when the baseline would point up-screen keeps the
// name right way up.
export function roofBasis(bg: Bearing, cw: Pt, h: number): string {
	let a = bg.cos + bg.sin;
	let b = (bg.cos - bg.sin) / 2;
	let c = bg.sin - bg.cos;
	let d = (bg.cos + bg.sin) / 2;
	if (a < 0) {
		a = -a;
		b = -b;
		c = -c;
		d = -d;
	}
	const o = P(cw[0], cw[1], h);
	return (
		`matrix(${a.toFixed(4)},${b.toFixed(4)},${c.toFixed(4)},${d.toFixed(4)},` +
		`${n1(o[0])},${n1(o[1])})`
	);
}

// The wall plane, the same idea one surface over. Local u runs along the wall's
// own ground direction; local v is straight down the screen, because z is
// screen-vertical only. One local unit is 1/ISO_X world units along the run,
// matching the roof, so both surfaces take the same font metrics. The origin is
// the wall's left-hand ground corner, which puts storey f at local y = -f·Z_UNIT
// — so every floor of a building shares one transform and differs only by a
// static offset that never has to be rewritten.
export function wallBasis(w: Wall): string {
	let ux = w.b[0] - w.a[0];
	let uy = w.b[1] - w.a[1];
	const L = Math.hypot(ux, uy) || 1;
	ux /= L;
	uy /= L;
	// start from whichever end keeps the text reading left to right; mirroring
	// the basis instead would mirror the glyphs with it
	const flip = ux - uy < 0;
	const A = flip ? w.b : w.a;
	if (flip) {
		ux = -ux;
		uy = -uy;
	}
	const o = P(A[0], A[1], 0);
	return (
		`matrix(${(ux - uy).toFixed(4)},${((ux + uy) / 2).toFixed(4)},0,1,` +
		`${n1(o[0])},${n1(o[1])})`
	);
}
