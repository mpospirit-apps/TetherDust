// The scene: the only thing that touches the DOM inside the <svg>.
//
// Built once per graph, then `layout()` rewrites geometry attributes for
// whatever bearing the camera is at. Nothing is created or destroyed on a turn,
// because a frame rewrites on the order of a thousand attributes and allocating
// through that would cost more than the arithmetic does.
//
// React owns the page, the chrome and the inspector; this owns the SVG and the
// animation frame. The two meet at createCityScene()'s return value and nowhere
// else.

import { type Camera, createCamera } from "./camera";
import {
	type Bearing,
	bearing,
	cornersOf,
	cylinder,
	ISO_X,
	ISO_Y,
	n1,
	P,
	type Pt,
	type Pt3,
	poly,
	px,
	py,
	roofBasis,
	rotPt,
	seam,
	shadeClass,
	type Wall,
	wallBasis,
	walls,
	Z_UNIT,
} from "./iso";
import { MONO_ADV, textPx, trimMid, wrapGlyphs } from "./labels";
import {
	diskScreenRx,
	diskScreenRy,
	diskSolidRadius,
	type Occluder,
	OccluderIndex,
} from "./occlude";
import {
	type Building,
	type Bundle,
	CAP_FONT,
	type City,
	capRoom,
	drumChars,
	FLOOR_BASE,
	FLOOR_FONT,
	FLOOR_PAD,
	ROOF_FONT,
	ROOF_PAD,
	ROOF_PAD_V,
	SIGN_FOOT,
	SIGN_H,
	SIGN_PAD_X,
	SIGN_POST,
	slabChars,
} from "./plan";
import {
	buildRun,
	flow,
	planRoute,
	ROUTE_EASE,
	type Route,
	type Run,
} from "./route";

const NS = "http://www.w3.org/2000/svg";

function mk<K extends keyof SVGElementTagNameMap>(
	tag: K,
	cls: string | null,
	parent: SVGElement,
): SVGElementTagNameMap[K] {
	const e = document.createElementNS(NS, tag);
	if (cls) e.setAttribute("class", cls);
	parent.appendChild(e);
	return e;
}

interface SlabRef {
	f: number;
	rel?: string;
	ws?: SVGPolygonElement[];
	roof?: SVGPolygonElement;
	side?: SVGPathElement;
	cap?: SVGEllipseElement;
}

interface WallSlot {
	wg: SVGGElement;
	poly: SVGPolygonElement;
	lines: SVGPathElement;
	bands: { f: number; el: SVGPolygonElement }[];
}

interface BuildingRef {
	b: Building;
	g: SVGGElement;
	solid: SVGGElement;
	slabG: SVGGElement;
	/** how far the stack is opened, in storey heights */
	spread: number;
	slabs?: SlabRef[];
	floorLift: number | null;
	occ: Occluder;
	depth: number;
	topY: number;
	screenX: number;
	roofTx: SVGTextElement;
	floors: SVGGElement;
	floorEls: SVGElement[];
	// slabs
	ws?: WallSlot[];
	roof?: SVGPolygonElement;
	roofIn?: SVGPolygonElement;
	// drums
	side?: SVGPathElement;
	seams?: SVGPathElement;
	cap?: SVGEllipseElement;
	bands?: { f: number; el: SVGPathElement }[];
	sign?: SVGGElement;
}

/** One drawn tether: the falloff, the hidden stretch, the ribbons, the ends. */
interface Cord {
	g: SVGGElement;
	layers: SVGPathElement[];
	ghost: SVGPathElement;
	sheath: SVGPathElement;
	core: SVGPathElement;
	nodes: [SVGCircleElement, SVGCircleElement];
	hw: number;
	phase: number;
	si: number;
	di: number;
	route: Route | null;
	run: Run | null;
}

/**
 * A bundle draws as one cord at rest and as its individual strands once either
 * end is opened — the same thing the explode does for storeys, one level up.
 * The strands are built the first time they are needed and kept afterwards.
 */
interface ArcRef {
	bu: Bundle;
	src: string;
	dst: string;
	g: SVGGElement;
	cord: Cord;
	strandG: SVGGElement;
	strands: Cord[] | null;
	split: boolean;
}

export interface SceneHandle {
	destroy(): void;
	/** re-place everything for the current bearing */
	layout(): void;
	setTheta(theta: number): void;
	theta(): number;
	viewBox(): { x: number; y: number; w: number; h: number };
	/** back to the fitted view */
	fit(): void;
	/** turn to the next quarter from wherever the camera was left */
	snap(dir: 1 | -1): void;
	nudge(radians: number): void;
	/** open a building, or pass null to close whatever is open */
	select(id: string | null): void;
	selected(): string | null;
}

// ── opening a building ───────────────────────────────────────────────────────
//
// Clicking lifts a building's storeys apart so the stack can be read a floor at
// a time. The bottom storey never moves: the city keeps its footprint and the
// skyline keeps its base, and everything above opens upward.
//
// How far it opens is capped by the headroom the frame has. The viewBox was
// fitted to the closed city, so a tall stack gets a narrower gap than a short
// one and both stay inside it.
/** storey heights of daylight between floors */
const EXPLODE_GAP = 0.72;
/** z units the tallest stack may grow by */
const EXPLODE_RISE = 4.6;
const EXPLODE_MS = 420;
const explodeOf = (h: number): number =>
	Math.min(EXPLODE_GAP, EXPLODE_RISE / Math.max(1, h - 1));

/** where storey f sits once the stack is opened by `spread` */
const floorZ = (r: BuildingRef, f: number): number => f * (1 + r.spread);
const topZ = (r: BuildingRef): number => (r.b.h - 1) * (1 + r.spread) + 1;

export function createCityScene(
	host: SVGSVGElement,
	city: City,
	onSelect?: (id: string | null) => void,
): SceneHandle {
	const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

	while (host.firstChild) host.removeChild(host.firstChild);
	// .anim gates the entrance fade, so reduced motion simply never opts in
	host.setAttribute("class", reduced ? "city" : "city anim");

	// A drum's shading can be baked once: a ground circle projects to the same
	// ellipse at every bearing, so the light across it never changes and a fixed
	// left-to-right gradient is exact rather than an approximation. The id is
	// scoped to this scene so two mounted cities cannot collide.
	const gradId = `cyl-${Math.random().toString(36).slice(2, 9)}`;
	const defs = mk("defs", null, host);
	const grad = mk("linearGradient", null, defs);
	grad.id = gradId;
	grad.setAttribute("x1", "0");
	grad.setAttribute("y1", "0");
	grad.setAttribute("x2", "1");
	grad.setAttribute("y2", "0");
	for (const [cls, off] of [
		["cyl-a", "0"],
		["cyl-b", "0.55"],
		["cyl-c", "1"],
	])
		mk("stop", cls, grad).setAttribute("offset", off);

	const cam = mk("g", null, host);
	const lCity = mk("g", null, cam);
	const lArcs = mk("g", "l-light", cam);
	const lLabels = mk("g", null, cam);

	// ── build ────────────────────────────────────────────────────────────────

	const bldRefs: BuildingRef[] = city.buildings.map((b) => {
		const g = mk("g", `bld bld--${b.kind}`, lCity);
		g.dataset.id = b.id;
		// the whole building as one solid, and — filled in only if it is ever
		// opened — the same building as a stack of storeys. They share a slot so
		// the labels and the hoarding still draw over whichever is showing.
		const solid = mk("g", null, g);
		const slabG = mk("g", null, g);
		const r: BuildingRef = {
			b,
			g,
			solid,
			slabG,
			spread: 0,
			floorLift: null,
			depth: 0,
			topY: 0,
			screenX: 0,
			occ: {
				id: b.id,
				disk: b.kind === "db",
				h: b.h,
				R: b.kind === "db" ? diskSolidRadius(b.r) : 0,
				cx: 0,
				cy: 0,
				x: b.x,
				y: b.y,
				w: b.w,
				d: b.d,
				x0: 0,
				x1: 0,
				y0: 0,
				y1: 0,
			},
			roofTx: null as unknown as SVGTextElement,
			floors: null as unknown as SVGGElement,
			floorEls: [],
		};

		if (b.kind === "db") {
			r.side = mk("path", "disk-side", solid);
			r.side.setAttribute("fill", `url(#${gradId})`);
			r.seams = mk("path", "disk-seam", solid);
			r.bands = [...b.lit].map(([f, rel]) => ({
				f,
				el: mk("path", `lit lit-${rel}`, solid),
			}));
			r.cap = mk("ellipse", "disk-cap", solid);
		} else {
			r.ws = [0, 1, 2, 3].map(() => {
				const wg = mk("g", null, solid);
				return {
					wg,
					poly: mk("polygon", "wall", wg),
					lines: mk("path", "floorline", wg),
					bands: [...b.lit].map(([f, rel]) => ({
						f,
						el: mk("polygon", `lit lit-${rel}`, wg),
					})),
				};
			});
			r.roof = mk("polygon", "roof", solid);
			r.roofIn = mk("polygon", "roof-in", solid);
		}

		if (b.kind === "code") {
			// the name lives on the slab itself, so there is no leader and nothing
			// floating above this half of the skyline. It sits against the near-left
			// corner rather than centred, so a short name and a long one start on
			// the same line down the district.
			r.roofTx = mk("text", "roof-label", g);
			r.roofTx.textContent = b.label;
			r.roofTx.setAttribute("font-size", String(ROOF_FONT));
			r.roofTx.setAttribute("x", n1((-b.w * ISO_X) / 2 + ROOF_PAD));
			r.roofTx.setAttribute("y", n1((b.d * ISO_X) / 2 - ROOF_PAD_V));
		} else {
			// A hoarding planted on the lid: two posts, a framed board, the name on
			// it. Every part is static in the cap's own frame, so layout() places the
			// whole thing with one translate — and because it never takes the roof
			// basis it stays square to the camera at any bearing.
			const sign = mk("g", "sign", g);
			r.sign = sign;
			const label = trimMid(
				b.label,
				Math.floor(capRoom(b.r) / (MONO_ADV * CAP_FONT)),
			);
			const sw = textPx(label, CAP_FONT) + 2 * SIGN_PAD_X;
			const foot = sw * SIGN_FOOT;
			const post = mk("path", "sign-post", sign);
			post.setAttribute(
				"d",
				`M${n1(-foot)},0V${n1(-SIGN_POST)}M${n1(foot)},0V${n1(-SIGN_POST)}`,
			);
			const board = mk("rect", "sign-board", sign);
			board.setAttribute("x", n1(-sw / 2));
			board.setAttribute("y", n1(-SIGN_POST - SIGN_H));
			board.setAttribute("width", n1(sw));
			board.setAttribute("height", n1(SIGN_H));
			r.roofTx = mk("text", "roof-label cap-label", sign);
			r.roofTx.textContent = label;
			r.roofTx.setAttribute("font-size", String(CAP_FONT));
			r.roofTx.setAttribute("text-anchor", "middle");
			r.roofTx.setAttribute("dominant-baseline", "central");
			r.roofTx.setAttribute("x", "0");
			r.roofTx.setAttribute("y", n1(-SIGN_POST - SIGN_H / 2));
		}

		// One storey, one name. Both surfaces put floor f at local y = -f·Z_UNIT,
		// so the whole stack lives under a single transform and layout() only ever
		// rewrites that one attribute per building.
		r.floors = mk("g", "floor-stack", g);
		if (b.kind === "db") {
			const rx = diskScreenRx(b.r);
			const ry = diskScreenRy(b.r);
			const maxChars = drumChars(b);
			r.floorEls = b.rows.map((row, f) => {
				const gg = mk(
					"g",
					b.lit.has(f) ? "floor-label hot" : "floor-label",
					r.floors,
				);
				const y0 = -(f * Z_UNIT + FLOOR_BASE);
				for (const q of wrapGlyphs(
					trimMid(row.name, maxChars),
					b.r,
					FLOOR_FONT,
					rx,
					ry,
					y0,
				)) {
					const t = mk("text", null, gg);
					t.textContent = q.ch;
					t.setAttribute("text-anchor", "middle");
					t.setAttribute(
						"transform",
						`translate(${n1(q.x)} ${n1(q.y)}) scale(${q.scale.toFixed(3)} 1)`,
					);
				}
				return gg as SVGElement;
			});
		} else {
			const maxChars = slabChars(b);
			r.floorEls = b.rows.map((row, f) => {
				const t = mk(
					"text",
					b.lit.has(f) ? "floor-label hot" : "floor-label",
					r.floors,
				);
				t.textContent = trimMid(row.name, maxChars);
				t.setAttribute("x", String(FLOOR_PAD));
				t.setAttribute("y", n1(-(f * Z_UNIT + FLOOR_BASE)));
				return t as SVGElement;
			});
		}
		return r;
	});
	const refById = new Map(bldRefs.map((r) => [r.b.id, r]));
	const occ = bldRefs.map((r) => r.occ);
	const index = new OccluderIndex();

	// Six strokes and two nodes make one tether. The order inside the group IS
	// the depth order: bloom outward, then the sheath, then the hot core.
	function makeCord(
		parent: SVGGElement,
		rel: string,
		conf: number,
		phase: number,
		si: number,
		di: number,
	): Cord {
		const w = 0.9 + Math.min(1, Math.max(0, conf)) * 2.1;
		const g = mk("g", `cord arc-${rel}`, parent);
		const part = (cls: string, sw: number): SVGPathElement => {
			const e = mk("path", `arc ${cls}`, g);
			e.setAttribute("stroke-width", sw.toFixed(2));
			return e;
		};
		// the order inside the group IS the depth order: bloom outward first,
		// then the sheath, then the hot core over the top
		const g3 = part("tt-g3", w * 9 + 15);
		const g2 = part("tt-g2", w * 5.4 + 8);
		const g1 = part("tt-g1", w * 3.1 + 4);
		const ghost = part("tt-ghost arc-ghost", w * 1.6);
		const g0 = part("tt-g0", w * 1.7 + 1.4);
		const sheath = mk("path", "tt-sheath", g);
		const core = mk("path", "tt-core", g);
		const n0 = mk("circle", "tt-node", g);
		const n1c = mk("circle", "tt-node", g);
		for (const c of [n0, n1c]) c.setAttribute("r", (1.6 + w * 0.6).toFixed(2));
		return {
			g,
			layers: [g0, g1, g2, g3],
			ghost,
			sheath,
			core,
			nodes: [n0, n1c],
			hw: 0.55 + w * 0.6,
			phase,
			si,
			di,
			route: null,
			run: null,
		};
	}

	const arcRefs: ArcRef[] = city.bundles.map((bu, i) => {
		const g = mk("g", "arc-g", lArcs);
		g.dataset.t = bu.id;
		const cord = makeCord(g, bu.rel, bu.conf, (i * 0.37) % 1, bu.si, bu.di);
		const strandG = mk("g", "strands", g);
		strandG.style.display = "none";
		return {
			bu,
			src: bu.src,
			dst: bu.dst,
			g,
			cord,
			strandG,
			strands: null,
			split: false,
		};
	});

	/**
	 * The per-storey geometry, built the first time a building is opened and kept
	 * afterwards. Every building carrying its own storeys from the start would
	 * cost more per frame than the whole rest of the scene, and most of it would
	 * never be looked at.
	 */
	function buildSlabs(r: BuildingRef): void {
		if (r.slabs) return;
		const b = r.b;
		r.slabs = b.rows.map((_row, f) => {
			const rel = b.lit.get(f);
			const g = mk("g", null, r.slabG);
			// a storey a tether lands on keeps reading as lit, so the whole slab
			// takes the relationship colour instead of carrying a band across it
			if (b.kind === "db") {
				const side = mk("path", rel ? `lit lit-${rel}` : "disk-side", g);
				if (!rel) side.setAttribute("fill", `url(#${gradId})`);
				return { f, rel, side, cap: mk("ellipse", "disk-cap", g) };
			}
			return {
				f,
				rel,
				ws: [0, 1, 2, 3].map(() => mk("polygon", "wall", g)),
				roof: mk("polygon", "roof", g),
			};
		});
	}

	/** the individual edges of a bundle, built the first time they are shown */
	function buildStrands(a: ArcRef): Cord[] {
		if (a.strands) return a.strands;
		a.strands = a.bu.strands.map((t, i) =>
			makeCord(a.strandG, t.rel, t.conf, (i * 0.29) % 1, t.si, t.di),
		);
		return a.strands;
	}

	const distRefs = city.districts.map((d) => ({
		d,
		el: mk("text", "district-label", lLabels),
	}));
	for (const dr of distRefs) dr.el.textContent = dr.d.label;

	// ── layout ───────────────────────────────────────────────────────────────

	let bg: Bearing = bearing(0, city.cx, city.cy);
	let lastOrder = "";
	let flowT = 0;
	let settleReq = 0;
	let frameReq = 0;
	let alive = true;

	function layout(): void {
		for (const r of bldRefs) {
			const b = r.b;
			const cw = rotPt(bg, b.cx, b.cy);
			const open = r.spread > 1e-4;
			r.solid.style.display = open ? "none" : "";
			r.slabG.style.display = open ? "" : "none";
			const hTop = topZ(r);
			let topY: number;

			if (b.kind === "db") {
				const cwx = px(cw[0], cw[1]);
				r.side?.setAttribute("d", cylinder(cw, b.r, 0, b.h));
				let sd = "";
				for (let f = 1; f < b.h; f++) sd += seam(cw, b.r, f);
				r.seams?.setAttribute("d", sd);
				for (const band of r.bands ?? [])
					band.el.setAttribute("d", cylinder(cw, b.r, band.f, band.f + 1));
				if (open && r.slabs) {
					for (const sl of r.slabs) {
						const z0 = floorZ(r, sl.f);
						sl.side?.setAttribute("d", cylinder(cw, b.r, z0, z0 + 1));
						const c = P(cw[0], cw[1], z0 + 1);
						sl.cap?.setAttribute("cx", n1(c[0]));
						sl.cap?.setAttribute("cy", n1(c[1]));
						sl.cap?.setAttribute("rx", n1(diskScreenRx(b.r)));
						sl.cap?.setAttribute("ry", n1(diskScreenRy(b.r)));
					}
				}
				const cap = P(cw[0], cw[1], hTop);
				r.cap?.setAttribute("cx", n1(cap[0]));
				r.cap?.setAttribute("cy", n1(cap[1]));
				r.cap?.setAttribute("rx", n1(diskScreenRx(b.r)));
				r.cap?.setAttribute("ry", n1(diskScreenRy(b.r)));
				// nearest point of a circle along the depth axis
				r.depth = cw[0] + cw[1] + b.r * Math.SQRT2;
				topY = cap[1];
				// Occlusion keeps the closed silhouette even while a stack is open, so
				// the screen box is the closed one too.
				const o = r.occ;
				const ery = diskScreenRy(b.r);
				o.cx = cw[0];
				o.cy = cw[1];
				o.x0 = cwx - diskScreenRx(b.r);
				o.x1 = cwx + diskScreenRx(b.r);
				o.y0 = py(cw[0], cw[1], b.h) - ery;
				o.y1 = py(cw[0], cw[1], 0) + ery;
				// the wrapped glyphs are static in the drum's own frame, so the whole
				// stack rides on this one translate
				r.floors.setAttribute(
					"transform",
					`translate(${n1(cap[0])} ${n1(py(cw[0], cw[1], 0))})`,
				);
				// the hoarding is rigid in the cap's frame, so it is only moved
				r.sign?.setAttribute(
					"transform",
					`translate(${n1(cap[0])} ${n1(cap[1])})`,
				);
			} else {
				const cs = cornersOf(bg, b.x, b.y, b.w, b.d);
				r.depth = Math.max(...cs.map((c) => c[0] + c[1]));
				const o = r.occ;
				o.x0 = Infinity;
				o.y0 = Infinity;
				o.x1 = -Infinity;
				o.y1 = -Infinity;
				for (const c of cs) {
					const X = px(c[0], c[1]);
					const yt = py(c[0], c[1], b.h);
					const yb = py(c[0], c[1], 0);
					if (X < o.x0) o.x0 = X;
					if (X > o.x1) o.x1 = X;
					if (yt < o.y0) o.y0 = yt;
					if (yb > o.y1) o.y1 = yb;
				}
				const ws = walls(cs);
				// edges 0 and 2 are the long ones; exactly one faces the camera, except
				// at the two bearings where both are edge-on and there is no wall to
				// write on at all
				const lw =
					ws[0].facing > 0.2 ? ws[0] : ws[2].facing > 0.2 ? ws[2] : null;
				r.floors.style.display = lw ? "" : "none";
				if (lw) r.floors.setAttribute("transform", wallBasis(lw));
				ws.forEach((w: Wall, i: number) => {
					const slot = (r.ws as WallSlot[])[i];
					if (w.facing <= 0.001) {
						slot.wg.style.display = "none";
						return;
					}
					slot.wg.style.display = "";
					slot.poly.setAttribute(
						"points",
						poly([
							P(w.a[0], w.a[1], b.h),
							P(w.b[0], w.b[1], b.h),
							P(w.b[0], w.b[1], 0),
							P(w.a[0], w.a[1], 0),
						]),
					);
					slot.poly.setAttribute("class", `wall ${shadeClass(w.shade)}`);
					let d = "";
					for (let f = 1; f < b.h; f++)
						d += `M${P(w.a[0], w.a[1], f)}L${P(w.b[0], w.b[1], f)}`;
					slot.lines.setAttribute("d", d);
					for (const band of slot.bands) {
						band.el.setAttribute(
							"points",
							poly([
								P(w.a[0], w.a[1], band.f + 1),
								P(w.b[0], w.b[1], band.f + 1),
								P(w.b[0], w.b[1], band.f),
								P(w.a[0], w.a[1], band.f),
							]),
						);
					}
				});
				r.roof?.setAttribute("points", poly(cs.map((c) => P(c[0], c[1], b.h))));
				r.roofIn?.setAttribute(
					"points",
					poly(
						cornersOf(bg, b.x + 0.16, b.y + 0.16, b.w - 0.32, b.d - 0.32).map(
							(c) => P(c[0], c[1], b.h),
						),
					),
				);
				if (open && r.slabs) {
					for (const sl of r.slabs) {
						const z0 = floorZ(r, sl.f);
						const z1 = z0 + 1;
						ws.forEach((w, i) => {
							const el = (sl.ws as SVGPolygonElement[])[i];
							if (w.facing <= 0.001) {
								el.style.display = "none";
								return;
							}
							el.style.display = "";
							el.setAttribute(
								"points",
								poly([
									P(w.a[0], w.a[1], z1),
									P(w.b[0], w.b[1], z1),
									P(w.b[0], w.b[1], z0),
									P(w.a[0], w.a[1], z0),
								]),
							);
							el.setAttribute(
								"class",
								sl.rel ? `lit lit-${sl.rel}` : `wall ${shadeClass(w.shade)}`,
							);
						});
						sl.roof?.setAttribute(
							"points",
							poly(cs.map((c) => P(c[0], c[1], z1))),
						);
					}
				}
				topY = P(cw[0], cw[1], hTop)[1];
			}

			if (b.kind === "code")
				r.roofTx.setAttribute("transform", roofBasis(bg, cw, hTop));
			// the names ride their own storey: both surfaces put floor f at local
			// y = -z·Z_UNIT, so opening the stack is one number per label
			if (r.floorLift !== r.spread) {
				r.floorLift = r.spread;
				r.floorEls.forEach((el, f) => {
					if (b.kind === "db")
						el.setAttribute(
							"transform",
							`translate(0 ${n1(-f * r.spread * Z_UNIT)})`,
						);
					else el.setAttribute("y", n1(-(floorZ(r, f) * Z_UNIT + FLOOR_BASE)));
				});
			}
			r.topY = topY;
			r.screenX = px(cw[0], cw[1]);
		}

		// painter's order changes with the angle — only touch the DOM when it does
		const order = bldRefs.slice().sort((a, b) => a.depth - b.depth);
		const key = order.map((r) => r.b.id).join();
		if (key !== lastOrder) {
			lastOrder = key;
			for (const r of order) lCity.appendChild(r.g);
		}

		// district labels ride above their own skyline, centred on it
		for (const dr of distRefs) {
			const rs = dr.d.members.map((b) => refById.get(b.id) as BuildingRef);
			const xs = rs.map((r) => r.screenX);
			dr.el.setAttribute("x", n1((Math.min(...xs) + Math.max(...xs)) / 2));
			dr.el.setAttribute("y", n1(Math.min(...rs.map((r) => r.topY)) - 46));
			dr.el.setAttribute("text-anchor", "middle");
		}

		index.rebuild(occ);
		routeTethers();
	}

	/**
	 * Re-plan every run for the current bearing, then ease onto the new route.
	 * The plan is a discrete choice, so it can jump when a building slides in or
	 * out of the way; easing turns that jump into a lean, which is also the only
	 * part of this that has to keep running after the camera stops — hence the
	 * settle frame. Buildings have not moved, so nothing else needs redrawing.
	 */
	function routeTethers(): void {
		const centre = new Map(
			bldRefs.map((r) => [r.b.id, rotPt(bg, r.b.cx, r.b.cy)] as const),
		);
		let easing = false;
		for (const a of arcRefs) {
			const s = refById.get(a.src) as BuildingRef;
			const d = refById.get(a.dst) as BuildingRef;
			const cs = centre.get(s.b.id) as Pt;
			const cd = centre.get(d.b.id) as Pt;
			const cords = a.split && a.strands ? a.strands : [a.cord];
			for (const c of cords) if (routeCord(c, s, d, cs, cd)) easing = true;
		}
		if (easing && !settleReq && alive) {
			settleReq = requestAnimationFrame(() => {
				settleReq = 0;
				if (alive) routeTethers();
			});
		}
	}

	/** returns true while the cord is still easing onto a newly chosen route */
	function routeCord(
		c: Cord,
		s: BuildingRef,
		d: BuildingRef,
		cs: Pt,
		cd: Pt,
	): boolean {
		// mid-storey, and mid-storey of an open stack is wherever that storey has
		// risen to — so a run that lands on floor 9 follows floor 9 up
		const zs = floorZ(s, c.si) + 0.5;
		const zd = floorZ(d, c.di) + 0.5;
		const w0 = anchor(s.b, zs, cd, zd);
		const w1 = anchor(d.b, zd, cs, zs);
		const want = planRoute(bg, index, w0, w1, s.b.id, d.b.id);
		let easing = false;
		if (!c.route || reduced) c.route = want;
		else if (
			Math.abs(want.lift - c.route.lift) < 0.02 &&
			Math.abs(want.lean - c.route.lean) < 0.02
		) {
			c.route = want;
		} else {
			c.route = {
				lift: c.route.lift + (want.lift - c.route.lift) * ROUTE_EASE,
				lean: c.route.lean + (want.lean - c.route.lean) * ROUTE_EASE,
			};
			easing = true;
		}
		const run = buildRun(bg, index, w0, w1, c.route, c.hw);
		c.run = run;
		for (const e of c.layers) e.setAttribute("d", run.solid);
		c.ghost.setAttribute("d", run.ghost);
		const last = run.pts.length - 1;
		c.nodes[0].setAttribute("cx", n1(run.pts[0][0]));
		c.nodes[0].setAttribute("cy", n1(run.pts[0][1]));
		c.nodes[1].setAttribute("cx", n1(run.pts[last][0]));
		c.nodes[1].setAttribute("cy", n1(run.pts[last][1]));
		c.nodes[0].style.visibility = run.hid[0] ? "hidden" : "";
		c.nodes[1].style.visibility = run.hid[last] ? "hidden" : "";
		paint(c, flowT);
		return easing;
	}

	function paint(c: Cord, time: number): void {
		if (!c.run) return;
		const rib = flow(c.run, time, c.phase);
		c.core.setAttribute("d", rib.core);
		c.sheath.setAttribute("d", rib.sheath);
	}

	/**
	 * A tether leaves from whichever face points most directly at the far end.
	 *
	 * The projection is anisotropic, so a direction in world space does NOT map
	 * to the same direction on screen — walking r along the world ray and
	 * projecting lands part-way round a drum instead of on the rim facing the
	 * target. Solve it on the projected ellipse instead: shoot a screen-space ray
	 * from the centre and take where it exits, then pull that screen offset back
	 * to a world offset, because occlusion needs a real 3D point.
	 */
	function anchor(b: Building, z: number, toward: Pt, towardZ: number): Pt3 {
		const c = rotPt(bg, b.cx, b.cy);
		if (b.kind === "db") {
			const from = P(c[0], c[1], z);
			const to = P(toward[0], toward[1], towardZ);
			let ux = to[0] - from[0];
			let uy = to[1] - from[1];
			const L = Math.hypot(ux, uy) || 1;
			ux /= L;
			uy /= L;
			const t = 1 / Math.hypot(ux / (b.r * ISO_X), uy / (b.r * ISO_Y));
			const p = (ux * t) / ISO_X;
			const q = (uy * t) / ISO_Y;
			return [c[0] + (p + q) / 2, c[1] + (q - p) / 2, z];
		}
		const cs = cornersOf(bg, b.x, b.y, b.w, b.d);
		let best: Wall | null = null;
		let bestDot = -Infinity;
		for (const w of walls(cs)) {
			if (w.facing <= 0.001) continue;
			const dot = w.nx * (toward[0] - c[0]) + w.ny * (toward[1] - c[1]);
			if (dot > bestDot) {
				bestDot = dot;
				best = w;
			}
		}
		if (!best) return [c[0], c[1], z];
		return [(best.a[0] + best.b[0]) / 2, (best.a[1] + best.b[1]) / 2, z];
	}

	// ── the frame the city is fitted to ──────────────────────────────────────
	//
	// Sized for every bearing at once, not the current one: the city turns inside
	// a fixed frame rather than the frame chasing it, so nothing drifts or
	// rescales as it rotates. A footprint sweeps a circle of radius rho about the
	// rotation centre, which projects to an ellipse.
	function unionBox(): { x: number; y: number; w: number; h: number } {
		let rho = 0;
		let maxH = 0;
		for (const b of city.buildings) {
			maxH = Math.max(maxH, b.h);
			if (b.kind === "db") {
				rho = Math.max(rho, Math.hypot(b.cx - city.cx, b.cy - city.cy) + b.r);
			} else {
				for (const q of [
					[b.x, b.y],
					[b.x + b.w, b.y],
					[b.x + b.w, b.y + b.d],
					[b.x, b.y + b.d],
				]) {
					rho = Math.max(rho, Math.hypot(q[0] - city.cx, q[1] - city.cy));
				}
			}
		}
		const c = P(city.cx, city.cy, 0);
		const ex = Math.SQRT2 * ISO_X * rho;
		const ey = Math.SQRT2 * ISO_Y * rho;
		// the tallest stack, its hoarding, and room for a tether arching over
		const lift = maxH * Z_UNIT + SIGN_POST + SIGN_H + 40;
		return {
			x: c[0] - ex - 70,
			y: c[1] - ey - lift,
			w: 2 * ex + 140,
			h: 2 * ey + lift + 60,
		};
	}

	const vb = unionBox();
	host.setAttribute(
		"viewBox",
		`${vb.x.toFixed(0)} ${vb.y.toFixed(0)} ${vb.w.toFixed(0)} ${vb.h.toFixed(0)}`,
	);

	// Storey names are only legible past a certain scale, and there are hundreds
	// of them. Gating the whole stack with display:none — rather than opacity on
	// each name — keeps every glyph out of the raster until it can be read.
	const FLOOR_MIN_PX = 5.4;
	function detail(scale: number): void {
		host.classList.toggle("detail", scale * FLOOR_FONT >= FLOOR_MIN_PX);
	}

	// ── selection ────────────────────────────────────────────────────────────
	//
	// One building is open at a time. Opening it splits every bundle it carries
	// into the individual edges, which then land on the storeys that have just
	// risen apart — the bundle collapses exactly when the view gains the room to
	// show what is inside it.
	const opening = new Map<
		BuildingRef,
		{ from: number; to: number; t0: number }
	>();
	let openRAF = 0;
	let selected: string | null = null;

	function spreadTo(r: BuildingRef, to: number): void {
		if (to > 0) buildSlabs(r);
		if (reduced) {
			r.spread = to;
			opening.delete(r);
			layout();
			return;
		}
		if (Math.abs(r.spread - to) < 1e-4) {
			opening.delete(r);
			return;
		}
		opening.set(r, { from: r.spread, to, t0: performance.now() });
		if (!openRAF) openRAF = requestAnimationFrame(openFrame);
	}

	function openFrame(now: number): void {
		openRAF = 0;
		if (!alive) return;
		for (const [r, a] of opening) {
			const u = Math.min(1, (now - a.t0) / EXPLODE_MS);
			r.spread = a.from + (a.to - a.from) * (1 - (1 - u) ** 3);
			if (u >= 1) {
				r.spread = a.to;
				opening.delete(r);
			}
		}
		layout();
		if (opening.size) openRAF = requestAnimationFrame(openFrame);
	}

	function setSplit(a: ArcRef, split: boolean): void {
		if (a.split === split) return;
		a.split = split;
		if (split) buildStrands(a);
		a.cord.g.style.display = split ? "none" : "";
		a.strandG.style.display = split ? "" : "none";
	}

	function select(id: string | null): void {
		selected = id;
		for (const r of bldRefs) {
			const on = r.b.id === id;
			r.g.classList.toggle("sel", on);
			if (!on && (r.spread > 0 || opening.has(r))) spreadTo(r, 0);
		}
		for (const a of arcRefs) {
			const rel = id !== null && (a.src === id || a.dst === id);
			a.g.classList.toggle("rel", rel);
			setSplit(a, rel);
		}
		host.classList.toggle("has-sel", id !== null);
		const r = id ? refById.get(id) : undefined;
		if (r) spreadTo(r, explodeOf(r.b.h));
		else layout();
		onSelect?.(id);
	}

	const camera: Camera = createCamera({
		host,
		cam,
		viewBox: vb,
		reduced,
		onTheta(t) {
			bg = bearing(t, city.cx, city.cy);
			layout();
		},
		onScale: detail,
		onPick(target) {
			const g = target?.closest(".bld");
			select(g instanceof SVGElement ? (g.dataset.id ?? null) : null);
		},
	});
	// a resize changes the apparent scale without any gesture having happened
	const ro = new ResizeObserver(() => detail(camera.scale()));
	ro.observe(host);

	layout();
	detail(camera.scale());
	requestAnimationFrame(() => {
		if (alive) host.classList.add("ready");
	});

	if (!reduced) {
		frameReq = requestAnimationFrame(function frame(now) {
			flowT = now / 1000;
			for (const a of arcRefs) {
				if (a.split && a.strands) for (const c of a.strands) paint(c, flowT);
				else paint(a.cord, flowT);
			}
			frameReq = requestAnimationFrame(frame);
		});
	}

	return {
		destroy() {
			alive = false;
			if (openRAF) cancelAnimationFrame(openRAF);
			camera.destroy();
			ro.disconnect();
			if (frameReq) cancelAnimationFrame(frameReq);
			if (settleReq) cancelAnimationFrame(settleReq);
			while (host.firstChild) host.removeChild(host.firstChild);
		},
		layout,
		setTheta(t: number) {
			bg = bearing(t, city.cx, city.cy);
			layout();
		},
		theta() {
			return bg.theta;
		},
		viewBox() {
			return vb;
		},
		select,
		selected: () => selected,
		fit: () => camera.fit(),
		snap: (dir) => camera.snap(dir),
		nudge: (r) => camera.nudge(r),
	};
}
