// Routing a tether, drawing it, and moving something through it.
//
// A tether is a quadratic Bezier whose control point is the world midpoint
// pushed off by (lean, lift) — sideways along the run's normal, and up:
//
//     W(t) = lerp(w0, w1) + 2t(1-t)·(lean·n̂, lift)
//
// P is affine, so this projects to a plain quadratic on screen: the same cheap
// curve as a screen-space one, except every point on it now has a real height
// and a real ground track — which is exactly what routing and occlusion need.

import { type Bearing, n1, P, type Pt, type Pt3, px, Z_UNIT } from "./iso";
import { clearZ, type OccluderIndex, occluded } from "./occlude";

// ── planning ─────────────────────────────────────────────────────────────────

/** z units; past this an arc stops reading as a link and starts reading as a rainbow */
const LIFT_CAP = 16;
/** daylight left over a roof, in z units */
const CLEAR_M = 0.6;
/** probes per candidate */
const ROUTE_N = 24;
/** straight first, then progressively wider, near side and far side */
const LEANS = [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6];
const LEAN_COST = 0.6;
const LIFT_COST = 0.05;
/** how fast a run eases onto a newly chosen route, per frame */
export const ROUTE_EASE = 0.22;

// An endpoint's own solid is not an obstacle in the same sense as any other: the
// anchor is ON it, so the run cannot be routed out from behind it — only routed
// out SOONER. Past the first tenth of the run that is worth doing (a steeper
// departure clears the roofline earlier); inside it nothing helps, and scoring
// it would just make every candidate look equally bad.
const SELF_R = 0.1;

const reqBuf = new Float64Array(ROUTE_N);

export interface Route {
	lift: number;
	lean: number;
}

/**
 * Lift alone cannot save every run: 2t(1−t) vanishes at the ends, so a
 * neighbour standing right next to an anchor would need a rainbow. Leaning the
 * control point sideways moves the ground track off that neighbour instead,
 * which costs a few world units rather than a hundred.
 */
export function planRoute(
	bg: Bearing,
	ix: OccluderIndex,
	w0: Pt3,
	w1: Pt3,
	skipA: string,
	skipB: string,
): Route {
	const S0 = P(w0[0], w0[1], w0[2]);
	const S1 = P(w1[0], w1[1], w1[2]);
	const base = (Math.hypot(S1[0] - S0[0], S1[1] - S0[1]) * 0.2 + 34) / Z_UNIT;
	let ux = w1[0] - w0[0];
	let uy = w1[1] - w0[1];
	const L = Math.hypot(ux, uy) || 1;
	ux /= L;
	uy /= L;
	let bLean = 0;
	let bLift = base;
	let bCost = Infinity;
	for (const lean of LEANS) {
		const ox = -uy * lean;
		const oy = ux * lean;
		let lift = base;
		for (let i = 1; i < ROUTE_N; i++) {
			const t = i / ROUTE_N;
			const k = 2 * t * (1 - t);
			const wx = w0[0] + (w1[0] - w0[0]) * t + k * ox;
			const wy = w0[1] + (w1[1] - w0[1]) * t + k * oy;
			const need = clearZ(
				bg,
				ix,
				wx,
				wy,
				px(wx, wy),
				t < SELF_R ? skipA : null,
				t > 1 - SELF_R ? skipB : null,
			);
			const r = (need + CLEAR_M - (w0[2] + (w1[2] - w0[2]) * t)) / k;
			reqBuf[i] = r;
			// ignore the demands that no lift within the cap could ever meet
			if (r <= LIFT_CAP && r > lift) lift = r;
		}
		let bad = 0;
		for (let i = 1; i < ROUTE_N; i++) if (lift < reqBuf[i]) bad++;
		const cost =
			(bad * 100) / ROUTE_N +
			(lift - base) * LIFT_COST +
			Math.abs(lean) * LEAN_COST;
		if (cost < bCost) {
			bCost = cost;
			bLean = lean;
			bLift = lift;
		}
		// clear, and no wider than the best so far: nothing further can beat it
		if (!bad && Math.abs(lean) <= Math.abs(bLean)) break;
	}
	return { lift: bLift, lean: bLean };
}

// ── drawing ──────────────────────────────────────────────────────────────────

/** fixed pitch of the rail the ribbons ride, in screen px */
export const RAIL_STEP = 8.5;

/** rail layout: x, y, nx, ny, s, half-width profile, hidden */
export const RAIL_STRIDE = 7;
export const R_X = 0;
export const R_Y = 1;
export const R_NX = 2;
export const R_NY = 3;
export const R_S = 4;
export const R_PROF = 5;
export const R_HID = 6;

export interface Run {
	/** screen samples of the curve */
	pts: Pt[];
	hid: boolean[];
	/** cumulative chord length, so a bolus travels at an even screen speed */
	cum: number[];
	len: number;
	rail: number[];
	/** the lit stretches, and the stretches behind something */
	solid: string;
	ghost: string;
}

const polyline = (pts: Pt[]): string =>
	`M${pts.map((p) => `${n1(p[0])},${n1(p[1])}`).join("L")}`;

/**
 * Walk the run, split it where visibility flips, and emit two paths: the seen
 * part solid, the hidden part as a faint ghost so a tether that dives behind
 * the skyline still reads as one connection.
 *
 * Nothing is excused, not even the building the run lands on. An anchor sits ON
 * its own wall, and the slab arithmetic already reads that honestly: from a
 * camera-facing face the ray leaves at once, from a face round the back it
 * passes straight through the solid. So a tether arriving behind its own
 * destination goes dashed all the way to the tip rather than surfacing for one
 * last solid stub.
 */
export function buildRun(
	bg: Bearing,
	ix: OccluderIndex,
	w0: Pt3,
	w1: Pt3,
	route: Route,
	hw: number,
): Run {
	const S0 = P(w0[0], w0[1], w0[2]);
	const S1 = P(w1[0], w1[1], w1[2]);
	const span = Math.hypot(S1[0] - S0[0], S1[1] - S0[1]);
	let ux = w1[0] - w0[0];
	let uy = w1[1] - w0[1];
	const L = Math.hypot(ux, uy) || 1;
	ux /= L;
	uy /= L;
	const ox = -uy * route.lean;
	const oy = ux * route.lean;
	const lift = route.lift;
	const N = Math.max(20, Math.min(56, Math.round(span / 14)));

	const at = (t: number): Pt3 => {
		const k = 2 * t * (1 - t);
		return [
			w0[0] + (w1[0] - w0[0]) * t + k * ox,
			w0[1] + (w1[1] - w0[1]) * t + k * oy,
			w0[2] + (w1[2] - w0[2]) * t + k * lift,
		];
	};
	const test = (t: number): { s: Pt; hid: boolean } => {
		const w = at(t);
		const s = P(w[0], w[1], w[2]);
		return { s, hid: occluded(bg, ix, w[0], w[1], w[2], s[0], s[1]) };
	};
	// bisect the flip so the cut lands on the silhouette, not on a sample
	const edgeAt = (t0: number, t1: number): Pt => {
		const want = test(t1).hid;
		let lo = t0;
		let hi = t1;
		for (let k = 0; k < 6; k++) {
			const m = (lo + hi) / 2;
			if (test(m).hid === want) hi = m;
			else lo = m;
		}
		return test((lo + hi) / 2).s;
	};

	const pts: Pt[] = new Array(N + 1);
	const hid: boolean[] = new Array(N + 1);
	for (let i = 0; i <= N; i++) {
		const r = test(i / N);
		pts[i] = r.s;
		hid[i] = r.hid;
	}

	let solid = "";
	let ghost = "";
	let cur = hid[0];
	let seg: Pt[] = [pts[0]];
	for (let i = 1; i <= N; i++) {
		if (hid[i] !== cur) {
			const bp = edgeAt((i - 1) / N, i / N);
			seg.push(bp);
			if (cur) ghost += polyline(seg);
			else solid += polyline(seg);
			cur = hid[i];
			seg = [bp];
		}
		seg.push(pts[i]);
	}
	if (cur) ghost += polyline(seg);
	else solid += polyline(seg);

	const cum: number[] = new Array(N + 1);
	cum[0] = 0;
	for (let i = 1; i <= N; i++) {
		cum[i] =
			cum[i - 1] +
			Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
	}
	const len = cum[N] || 1;

	// The rail: fixed pitch in screen length, carrying position, unit normal,
	// distance along the run, the half-width profile, and — tested HERE rather
	// than inherited from the run's own coarser sampling — whether that exact
	// point is behind anything. Inheriting it cost the ribbon a whole run segment
	// at every silhouette, which is why a tether could stop a good way short of
	// the wall it lands on.
	const M = Math.max(4, Math.round(len / RAIL_STEP));
	const rail: number[] = [];
	let sg = 1;
	// the bisection below queries backwards as well as forwards, so this has to
	// be able to walk either way rather than only ratchet up
	const tAt = (sl: number): number => {
		while (sg < N && cum[sg] < sl) sg++;
		while (sg > 1 && cum[sg - 1] > sl) sg--;
		return (sg - 1 + (sl - cum[sg - 1]) / (cum[sg] - cum[sg - 1] || 1)) / N;
	};
	const put = (sl: number, sc: Pt, hidden: boolean): void => {
		const dl = cum[sg] - cum[sg - 1] || 1;
		const u = sl / len;
		rail.push(
			sc[0],
			sc[1],
			-(pts[sg][1] - pts[sg - 1][1]) / dl,
			(pts[sg][0] - pts[sg - 1][0]) / dl,
			sl,
			// max(0, …): j·len/M can land a hair over len, and sqrt of a hair below
			// zero is NaN, which would reach the path data as "NaN,NaN"
			Math.max(
				0.4,
				hw * (0.26 + 0.74 * Math.sqrt(Math.max(0, Math.sin(Math.PI * u)))),
			),
			hidden ? 1 : 0,
		);
	};
	let prevS = 0;
	let prevHid: boolean | null = null;
	for (let j = 0; j <= M; j++) {
		const sl = (j * len) / M;
		const q = test(tAt(sl));
		// The drawn run bisects its silhouette crossings so the cut lands on the
		// edge and not on a sample; without the same treatment here the ribbon
		// would still stop up to a rail step early, which at four times zoom is a
		// visible gap. So a flip inserts the crossing itself, on the lit side.
		if (prevHid !== null && q.hid !== prevHid) {
			let lo = prevS;
			let hi = sl;
			for (let k = 0; k < 6; k++) {
				const mid = (lo + hi) / 2;
				if (test(tAt(mid)).hid === q.hid) hi = mid;
				else lo = mid;
			}
			const edge = (lo + hi) / 2;
			put(edge, test(tAt(edge - (q.hid ? 1e-3 : 0))).s, false);
		}
		put(sl, q.s, q.hid);
		prevS = sl;
		prevHid = q.hid;
	}

	return { pts, hid, cum, len, rail, solid, ghost };
}

// ── flow ─────────────────────────────────────────────────────────────────────
//
// A stroke is one width for its whole length, which is what makes a tether read
// as line art. The two body layers are outlines instead: out along one side with
// the width profile, back along the other, closed — one closed loop per visible
// stretch, so a run that dives behind a building still breaks where it should.
//
// Motion is peristaltic rather than decorative. A couple of boluses travel the
// run and the profile swells as each passes, so the tether reads as something
// moving THROUGH it rather than as particles riding on top of it.

/** boluses in flight at once */
const SWELL_N = 2;
/** how much fatter the run gets as one passes */
const SWELL_AMT = 0.95;
/** px of run a bolus occupies */
const SWELL_LEN = 105;
/** seconds, source to destination */
const SWELL_PERIOD = 6.4;
/** the sheath is this much wider than the core */
export const SHEATH = 2.15;

const pos = new Float64Array(SWELL_N);

export interface Ribbons {
	core: string;
	sheath: string;
}

export function flow(run: Run, time: number, phase: number): Ribbons {
	const r = run.rail;
	const travel = run.len + 2 * SWELL_LEN;
	for (let m = 0; m < SWELL_N; m++) {
		const u = (time / SWELL_PERIOD + phase + m / SWELL_N) % 1;
		pos[m] = -SWELL_LEN + u * travel;
	}
	let dc = "";
	let ds = "";
	let fc = "";
	let bc = "";
	let fs = "";
	let bs = "";
	let n = 0;
	const flush = (): void => {
		if (n > 1) {
			dc += `M${fc}${bc}Z`;
			ds += `M${fs}${bs}Z`;
		}
		fc = "";
		bc = "";
		fs = "";
		bs = "";
		n = 0;
	};
	for (let i = 0; i < r.length; i += RAIL_STRIDE) {
		if (r[i + R_HID]) {
			flush();
			continue;
		}
		let k = 1;
		for (let m = 0; m < SWELL_N; m++) {
			const q = (r[i + R_S] - pos[m]) / SWELL_LEN;
			if (q > -1 && q < 1) {
				const b = 1 - q * q;
				k += SWELL_AMT * b * b;
			}
		}
		const h = r[i + R_PROF] * k;
		const nx = r[i + R_NX] * h;
		const ny = r[i + R_NY] * h;
		const x = r[i + R_X];
		const y = r[i + R_Y];
		fc += `${n ? "L" : ""}${n1(x + nx)},${n1(y + ny)}`;
		bc = `L${n1(x - nx)},${n1(y - ny)}${bc}`;
		const hx = nx * SHEATH;
		const hy = ny * SHEATH;
		fs += `${n ? "L" : ""}${n1(x + hx)},${n1(y + hy)}`;
		bs = `L${n1(x - hx)},${n1(y - hy)}${bs}`;
		n++;
	}
	flush();
	return { core: dc, sheath: ds };
}
