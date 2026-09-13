// Occlusion, and its inverse.
//
// A fixed 2:1 dimetric camera has one null direction: solving P(v) = 0 gives
// v = (1, 1, ZK). Every world point sharing a pixel with p lies on p + s·v, and
// +v points at the camera. So "is this bit of tether hidden?" is a ray cast
// along v against the building solids — exact, with no depth sorting to get
// wrong, and correct at every bearing for free.
//
// Boxes are axis-aligned in *unrotated* world space, so the single ray is
// rotated back rather than every footprint being rotated forward. A disk stays
// a circle under rotation and is tested where it stands.

import { type Bearing, ISO_X, ISO_Y, unrotPt, ZK } from "./iso";

export const RAY_EPS = 1e-3;

export interface Occluder {
	id: string;
	disk: boolean;
	/** height in storeys */
	h: number;
	/** disks: radius of the solid, and its centre in *rotated* world space */
	R: number;
	cx: number;
	cy: number;
	/** slabs: the footprint in *unrotated* world space */
	x: number;
	y: number;
	w: number;
	d: number;
	/** screen bounding box, rewritten every frame */
	x0: number;
	x1: number;
	y0: number;
	y1: number;
}

/**
 * A ground circle of world radius R projects to an ellipse of semi-axis
 * √2·R·ISO_X, so the solid standing behind a drum drawn with semi-axis r·ISO_X
 * has world radius r/√2. Getting this wrong makes drums occlude a shape that is
 * not the one on screen.
 */
export const diskSolidRadius = (drawnR: number): number =>
	drawnR * Math.SQRT1_2;

/** the drawn ellipse's semi-axes, for the same drum */
export const diskScreenRx = (drawnR: number): number => drawnR * ISO_X;
export const diskScreenRy = (drawnR: number): number => drawnR * ISO_Y;

// ── the screen-x index ───────────────────────────────────────────────────────
//
// The camera ray projects to (0, ±1): a point's screen x never changes along it.
// Only a building whose own pixels span that column can possibly be in the way,
// so bucketing occluders by screen x is an *exact* filter, not an
// approximation — it turns an O(all buildings) reject into O(the few that
// overlap this column).

const BIN_PX = 64;

export class OccluderIndex {
	private bins: Occluder[][] = [];
	private minX = 0;
	private all: Occluder[] = [];

	/** call once per frame, after the occluders' screen boxes are up to date */
	rebuild(occ: Occluder[]): void {
		this.all = occ;
		if (occ.length === 0) {
			this.bins = [];
			return;
		}
		let lo = Infinity;
		let hi = -Infinity;
		for (const o of occ) {
			if (o.x0 < lo) lo = o.x0;
			if (o.x1 > hi) hi = o.x1;
		}
		this.minX = lo;
		const n = Math.max(1, Math.ceil((hi - lo) / BIN_PX) + 1);
		const bins: Occluder[][] = new Array(n);
		for (let i = 0; i < n; i++) bins[i] = [];
		for (const o of occ) {
			const a = Math.max(0, Math.floor((o.x0 - lo) / BIN_PX));
			const b = Math.min(n - 1, Math.floor((o.x1 - lo) / BIN_PX));
			for (let i = a; i <= b; i++) bins[i].push(o);
		}
		this.bins = bins;
	}

	at(sx: number): readonly Occluder[] {
		const i = Math.floor((sx - this.minX) / BIN_PX);
		if (i < 0 || i >= this.bins.length) return EMPTY;
		return this.bins[i];
	}

	/** every occluder, for the unindexed path a check can compare against */
	get occluders(): readonly Occluder[] {
		return this.all;
	}
}

const EMPTY: readonly Occluder[] = [];

// ── the two solids ───────────────────────────────────────────────────────────

/** slab-ray overlap, in unrotated world space */
function hitsBox(
	bg: Bearing,
	qx: number,
	qy: number,
	qz: number,
	o: Occluder,
): boolean {
	let s0 = RAY_EPS;
	let s1 = Infinity;
	let lo: number;
	let hi: number;
	let t: number;
	if (Math.abs(bg.rx) < 1e-9) {
		if (qx < o.x || qx > o.x + o.w) return false;
	} else {
		lo = (o.x - qx) / bg.rx;
		hi = (o.x + o.w - qx) / bg.rx;
		if (lo > hi) {
			t = lo;
			lo = hi;
			hi = t;
		}
		if (lo > s0) s0 = lo;
		if (hi < s1) s1 = hi;
	}
	if (Math.abs(bg.ry) < 1e-9) {
		if (qy < o.y || qy > o.y + o.d) return false;
	} else {
		lo = (o.y - qy) / bg.ry;
		hi = (o.y + o.d - qy) / bg.ry;
		if (lo > hi) {
			t = lo;
			lo = hi;
			hi = t;
		}
		if (lo > s0) s0 = lo;
		if (hi < s1) s1 = hi;
	}
	// ZK > 0, so the z slab arrives already in order
	lo = -qz / ZK;
	hi = (o.h - qz) / ZK;
	if (lo > s0) s0 = lo;
	if (hi < s1) s1 = hi;
	return s0 <= s1;
}

/** drum-ray overlap, in rotated world space, where the circle is still a circle */
function hitsDisk(wx: number, wy: number, wz: number, o: Occluder): boolean {
	const ax = wx - o.cx;
	const ay = wy - o.cy;
	const half = ax + ay;
	const disc = half * half - 2 * (ax * ax + ay * ay - o.R * o.R);
	if (disc <= 0) return false;
	const sq = Math.sqrt(disc);
	let s0 = (-half - sq) / 2;
	let s1 = (-half + sq) / 2;
	if (RAY_EPS > s0) s0 = RAY_EPS;
	const zl = -wz / ZK;
	const zh = (o.h - wz) / ZK;
	if (zl > s0) s0 = zl;
	if (zh < s1) s1 = zh;
	return s0 <= s1;
}

/**
 * Is this world point hidden? The screen box is a cheap reject on top of the
 * column index: a point outside a building's own pixels can never be behind it.
 */
export function occluded(
	bg: Bearing,
	ix: OccluderIndex,
	wx: number,
	wy: number,
	wz: number,
	sx: number,
	sy: number,
): boolean {
	const q = unrotPt(bg, wx, wy);
	for (const o of ix.at(sx)) {
		if (sx < o.x0 || sx > o.x1 || sy < o.y0 || sy > o.y1) continue;
		if (o.disk ? hitsDisk(wx, wy, wz, o) : hitsBox(bg, q[0], q[1], wz, o))
			return true;
	}
	return false;
}

/**
 * The same slab arithmetic run backwards. `occluded` asks "is this point
 * hidden?"; routing wants the cheaper question "how high would it have to be to
 * get out from behind everything?", which the slabs answer directly: a solid
 * whose ray-entry is s0 stops covering the pixel once z passes h − s0·ZK, and
 * the tallest such demand along the way is what the curve has to clear. One
 * pass over the ground track therefore yields the exact lift a run needs — no
 * candidate curves to test, no bisection.
 *
 * `skipA` / `skipB` exclude a run's own endpoints: the anchor sits on its own
 * wall and cannot be routed out from behind it, only made to arrive sooner.
 */
export function clearZ(
	bg: Bearing,
	ix: OccluderIndex,
	wx: number,
	wy: number,
	sx: number,
	skipA: string | null,
	skipB: string | null,
): number {
	const q = unrotPt(bg, wx, wy);
	const qx = q[0];
	const qy = q[1];
	let need = 0;
	for (const o of ix.at(sx)) {
		if (o.id === skipA || o.id === skipB || sx < o.x0 || sx > o.x1) continue;
		let s0 = RAY_EPS;
		let s1 = Infinity;
		let lo: number;
		let hi: number;
		let t: number;
		if (o.disk) {
			const ax = wx - o.cx;
			const ay = wy - o.cy;
			const half = ax + ay;
			const disc = half * half - 2 * (ax * ax + ay * ay - o.R * o.R);
			if (disc <= 0) continue;
			const sq = Math.sqrt(disc);
			lo = (-half - sq) / 2;
			hi = (-half + sq) / 2;
			if (lo > s0) s0 = lo;
			if (hi < s1) s1 = hi;
		} else {
			if (Math.abs(bg.rx) < 1e-9) {
				if (qx < o.x || qx > o.x + o.w) continue;
			} else {
				lo = (o.x - qx) / bg.rx;
				hi = (o.x + o.w - qx) / bg.rx;
				if (lo > hi) {
					t = lo;
					lo = hi;
					hi = t;
				}
				if (lo > s0) s0 = lo;
				if (hi < s1) s1 = hi;
			}
			if (Math.abs(bg.ry) < 1e-9) {
				if (qy < o.y || qy > o.y + o.d) continue;
			} else {
				lo = (o.y - qy) / bg.ry;
				hi = (o.y + o.d - qy) / bg.ry;
				if (lo > hi) {
					t = lo;
					lo = hi;
					hi = t;
				}
				if (lo > s0) s0 = lo;
				if (hi < s1) s1 = hi;
			}
		}
		if (s0 > s1) continue;
		const z = o.h - s0 * ZK;
		if (z > need) need = z;
	}
	return need;
}
