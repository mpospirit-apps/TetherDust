// Turning a tether graph into a city.
//
// Buildings are code files (slabs) and database tables (drums); their storeys
// are the symbols and columns beneath them; edges become tethers. The schema
// allows more shapes than that reading assumes, so every case is decided here
// rather than left to whatever the geometry happens to do with it.
//
// Nothing in this module is random. Sizes come from a hash of the node id, so
// the same graph always produces the same city and a screenshot can be read
// back against the graph it came from.

import type { GraphEdge, GraphNode, TetherGraph } from "../types";
import { ISO_X } from "./iso";
import { MONO_ADV, textPx } from "./labels";
import { diskSolidRadius } from "./occlude";

export type Rel = GraphEdge["relationship"];
export type Kind = "code" | "db";

const REL_ORDER: Rel[] = ["reads", "writes", "references", "maps-to"];

// ── type sizes ───────────────────────────────────────────────────────────────

/** local units in the roof plane */
export const ROOF_FONT = 17;
export const ROOF_PAD = 7;
export const ROOF_PAD_V = 6;
/** every storey carries its own name, on a wall or wrapped round a drum */
export const FLOOR_FONT = 7;
export const FLOOR_PAD = 5;
export const FLOOR_BASE = 3;
/** a cap is a small surface and a table name is a long string, so it sizes itself */
export const CAP_FONT = 13;
export const CAP_R_MAX = 2.6;
/** a hoarding is wider than the posts it stands on */
export const CAP_USABLE = 1.6;
export const SIGN_PAD_X = 8;
export const SIGN_PAD_Y = 5;
export const SIGN_POST = 15;
export const SIGN_FOOT = 0.27;
/** capNeed inverts capRoom exactly, so give it room to clear its own floor() */
const CAP_SLACK = 1.04;
export const SIGN_H = CAP_FONT + 2 * SIGN_PAD_Y;

/** facing width : depth */
const FACE_RATIO = 3;
/** world units of clear space between the districts */
const CHANNEL = 5.5;

// The label sets a MINIMUM length, not the length. A second, salted draw from
// the same hash pushes each slab past it, and the depth draws independently, so
// two files with the same length of name still come out different shapes.
const CODE_W_SPREAD = 0.34;
const CODE_D_MIN = 1.45;
const CODE_D_MAX = 4.4;
// A drum has one dimension to play with, so the spread all lands there: fan-in
// and the cap label each set a floor and the hash pushes out past it. Height is
// off limits — that is the column count.
const DB_R_BASE = 0.85;
const DB_R_FAN = 0.16;
const DB_R_SPREAD = 0.85;

export const capRoom = (r: number): number =>
	2 * r * ISO_X * CAP_USABLE - 2 * SIGN_PAD_X;
/** and the drum has to be big enough to carry its own board — capRoom inverted,
 *  so the two can never drift apart */
const capNeed = (label: string): number =>
	(textPx(label, CAP_FONT) * CAP_SLACK + 2 * SIGN_PAD_X) /
	(2 * ISO_X * CAP_USABLE);

// ── the model ────────────────────────────────────────────────────────────────

export interface Storey {
	id: string;
	name: string;
	type: string;
	pk: boolean;
	fk: boolean;
	node: GraphNode | null;
}

/** one graph edge, once both its ends have been resolved to a storey */
export interface Strand {
	edge: GraphEdge;
	rel: Rel;
	conf: number;
	/** storey index at each end */
	si: number;
	di: number;
	/** false when that end named only the file or table, not a symbol or column */
	namedSrc: boolean;
	namedDst: boolean;
}

/**
 * Every edge between one pair of buildings, drawn as a single tether. In the one
 * real graph measured, 66 edges collapse to 13 pairs and the busiest pair
 * carries 12 — drawn individually they retrace each other into a haystack. The
 * strands separate onto their own storeys when the building is opened.
 */
export interface Bundle {
	id: string;
	src: string;
	dst: string;
	strands: Strand[];
	/** the relationship most of the strands agree on */
	rel: Rel;
	conf: number;
	/** where the collapsed bundle attaches: the mean of its strands' storeys */
	si: number;
	di: number;
}

export interface Building {
	id: string;
	kind: Kind;
	/** the full name: a file path, or a schema-qualified table */
	name: string;
	/** what actually gets painted: a basename, or a de-prefixed table */
	label: string;
	block: string;
	desc: string;
	rows: Storey[];
	h: number;
	/** storey → the relationship of an edge that lands on it */
	lit: Map<number, Rel>;
	bundles: Bundle[];
	/** how many individual edges touch this building */
	fanIn: number;
	// geometry, filled in by the packer
	r: number;
	w: number;
	d: number;
	cx: number;
	cy: number;
	x: number;
	y: number;
}

export interface District {
	id: string;
	kind: Kind;
	label: string;
	members: Building[];
}

export interface City {
	buildings: Building[];
	byId: Map<string, Building>;
	bundles: Bundle[];
	districts: District[];
	/** rotation centre, in world coordinates */
	cx: number;
	cy: number;
	/** edges that resolved to a single building and had nowhere to go */
	dropped: number;
	codebaseSummary: string;
	databaseSummary: string;
}

export interface PlanOptions {
	codeLabel?: string;
	dataLabel?: string;
}

// ── the hash ─────────────────────────────────────────────────────────────────

/**
 * A stable hash of the node id, NOT Math.random(): the city has to come back
 * identical on every reload. FNV-1a → [0, 1).
 */
export function jitter(id: string): number {
	let h = 2166136261;
	for (let i = 0; i < id.length; i++) {
		h ^= id.charCodeAt(i);
		h = Math.imul(h, 16777619);
	}
	return ((h >>> 0) % 10000) / 10000;
}

// ── naming ───────────────────────────────────────────────────────────────────

const basename = (s: string): string => s.split("/").pop() ?? s;
const dirname = (s: string): string => {
	const i = s.lastIndexOf("/");
	return i > 0 ? s.slice(0, i) : "";
};

/**
 * Tables arrive schema-qualified (`engine_reportexecution`) and the prefix eats
 * half of a cap. Strip the leading segment where it prefixes more than one
 * table — derived from the set, so it adapts to any schema and still leaves a
 * lone `auth_user` or `query_log` intact.
 */
function tableLabeller(names: string[]): (s: string) => string {
	const seen = new Map<string, number>();
	for (const n of names) {
		const i = n.indexOf("_");
		if (i > 0) {
			const p = n.slice(0, i);
			seen.set(p, (seen.get(p) ?? 0) + 1);
		}
	}
	return (n: string) => {
		const i = n.indexOf("_");
		return i > 0 && (seen.get(n.slice(0, i)) ?? 0) > 1 ? n.slice(i + 1) : n;
	};
}

const roofWorld = (s: string): number =>
	(textPx(s, ROOF_FONT) + 2 * ROOF_PAD) / ISO_X;
const floorWorld = (rows: Storey[]): number =>
	(Math.max(...rows.map((r) => textPx(r.name, FLOOR_FONT))) + 2 * FLOOR_PAD) /
	ISO_X;

// ── graph → buildings ────────────────────────────────────────────────────────

const PARENT_OF: Record<string, string> = {
	"code-symbol": "code-file",
	"db-column": "db-table",
};

function storeyOf(n: GraphNode): Storey {
	return {
		id: n.id,
		name: n.label,
		type: n.data_type ?? "",
		pk: n.primary_key === true,
		fk: typeof n.foreign_key === "string" && n.foreign_key.length > 0,
		node: n,
	};
}

export function planCity(graph: TetherGraph, opts: PlanOptions = {}): City {
	const nodes = graph.nodes ?? [];
	const byNode = new Map(nodes.map((n) => [n.id, n]));

	// 1. buildings, in the order the agent listed them
	const buildings: Building[] = [];
	const byId = new Map<string, Building>();
	for (const n of nodes) {
		const kind: Kind | null =
			n.kind === "code-file" ? "code" : n.kind === "db-table" ? "db" : null;
		if (!kind) continue;
		const name = kind === "code" ? (n.path ?? n.label) : n.label;
		const b: Building = {
			id: n.id,
			kind,
			name,
			label: kind === "code" ? basename(name) : name,
			block: kind === "code" ? dirname(name) : (n.schema ?? "public"),
			desc: n.description ?? "",
			rows: [],
			h: 0,
			lit: new Map(),
			bundles: [],
			fanIn: 0,
			r: 0,
			w: 0,
			d: 0,
			cx: 0,
			cy: 0,
			x: 0,
			y: 0,
		};
		buildings.push(b);
		byId.set(b.id, b);
	}

	// 2. storeys. The schema carries no ordinal, so this is the order the agent
	//    listed them in — stable for a given graph version, which is enough.
	const storeyAt = new Map<string, { b: Building; i: number }>();
	for (const n of nodes) {
		const want = PARENT_OF[n.kind];
		if (!want || !n.parent_id) continue;
		const parent = byId.get(n.parent_id);
		if (!parent || byNode.get(n.parent_id)?.kind !== want) continue;
		storeyAt.set(n.id, { b: parent, i: parent.rows.length });
		parent.rows.push(storeyOf(n));
	}
	// a building with nothing under it still needs a body to draw
	for (const b of buildings) {
		if (b.rows.length === 0) {
			b.rows.push({
				id: `${b.id}~only`,
				name: b.label,
				type: "",
				pk: false,
				fk: false,
				node: null,
			});
		}
		b.h = b.rows.length;
	}

	// 3. the table labeller needs the whole set before any drum can be sized
	const strip = tableLabeller(
		buildings.filter((b) => b.kind === "db").map((b) => b.name),
	);
	for (const b of buildings) if (b.kind === "db") b.label = strip(b.name);

	// 4. edges → strands, bundled by the pair of buildings they join
	const bundles: Bundle[] = [];
	const byPair = new Map<string, Bundle>();
	let dropped = 0;
	for (const e of graph.edges ?? []) {
		const a = resolveEnd(e.source_id, storeyAt, byId);
		const z = resolveEnd(e.target_id, storeyAt, byId);
		if (!a || !z) continue;
		if (a.b === z.b) {
			// a self-loop has nowhere to go; counted rather than silently lost
			dropped++;
			continue;
		}
		const rel = e.relationship;
		const conf = typeof e.confidence === "number" ? e.confidence : 1;
		// unordered key: two buildings are connected, whichever way each edge runs
		const flip = a.b.id > z.b.id;
		const src = flip ? z.b : a.b;
		const dst = flip ? a.b : z.b;
		const key = `${src.id} ${dst.id}`;
		let bundle = byPair.get(key);
		if (!bundle) {
			bundle = {
				id: key,
				src: src.id,
				dst: dst.id,
				strands: [],
				rel,
				conf,
				si: 0,
				di: 0,
			};
			byPair.set(key, bundle);
			bundles.push(bundle);
			src.bundles.push(bundle);
			dst.bundles.push(bundle);
		}
		bundle.strands.push({
			edge: e,
			rel,
			conf,
			si: flip ? z.i : a.i,
			di: flip ? a.i : z.i,
			namedSrc: flip ? z.named : a.named,
			namedDst: flip ? a.named : z.named,
		});
		src.fanIn++;
		dst.fanIn++;
		// Every storey an edge actually names lights up, bundled or not: the drum
		// shows which columns are touched even while one cord stands for twelve.
		if (flip ? z.named : a.named) src.lit.set(flip ? z.i : a.i, rel);
		if (flip ? a.named : z.named) dst.lit.set(flip ? a.i : z.i, rel);
	}
	for (const bundle of bundles) {
		bundle.rel = dominantRel(bundle.strands);
		bundle.conf =
			bundle.strands.reduce((s, t) => s + t.conf, 0) / bundle.strands.length;
		bundle.si = meanStorey(bundle.strands.map((t) => t.si));
		bundle.di = meanStorey(bundle.strands.map((t) => t.di));
	}

	// 5. size every footprint from its own name and its own hash
	for (const b of buildings) {
		if (b.kind === "db") {
			b.r = Math.min(
				CAP_R_MAX,
				Math.max(
					(DB_R_BASE + Math.min(b.fanIn, 4) * DB_R_FAN) *
						(1 + jitter(b.id) * DB_R_SPREAD),
					capNeed(b.label),
				),
			);
			b.w = b.r * 2;
			b.d = b.r * 2;
		} else {
			b.w =
				Math.max(roofWorld(b.label), floorWorld(b.rows)) *
				(1 + jitter(`${b.id}~w`) * CODE_W_SPREAD);
			b.d = CODE_D_MIN + jitter(b.id) * (CODE_D_MAX - CODE_D_MIN);
		}
	}

	// 6. two districts, facing each other across a channel
	const codeMembers = buildings.filter((b) => b.kind === "code");
	const dbMembers = buildings.filter((b) => b.kind === "db");
	const codeBox = packDistrict(codeMembers, 0.45, 1.65, true);
	// The data district is spaced wider: its boards run up to 1.55x the width of
	// the drum they stand on, so the drums need room the drums themselves do not.
	const dbBox = packDistrict(dbMembers, 1.9, 1.9, false);
	const dx = codeBox.maxX + CHANNEL - dbBox.minX;
	for (const b of dbMembers) b.cx += dx;
	const dy = (codeBox.extentY - dbBox.extentY) / 2;
	for (const b of dy > 0 ? dbMembers : codeMembers) b.cy += Math.abs(dy);
	for (const b of buildings) {
		b.x = b.cx - b.w / 2;
		b.y = b.cy - b.d / 2;
	}

	let lo = Infinity;
	let hi = -Infinity;
	let loY = Infinity;
	let hiY = -Infinity;
	for (const b of buildings) {
		if (b.x < lo) lo = b.x;
		if (b.x + b.w > hi) hi = b.x + b.w;
		if (b.y < loY) loY = b.y;
		if (b.y + b.d > hiY) hiY = b.y + b.d;
	}

	const districts: District[] = [];
	if (codeMembers.length)
		districts.push({
			id: "code",
			kind: "code",
			label: opts.codeLabel ?? "codebase",
			members: codeMembers,
		});
	if (dbMembers.length)
		districts.push({
			id: "data",
			kind: "db",
			label: opts.dataLabel ?? "database",
			members: dbMembers,
		});

	return {
		buildings,
		byId,
		bundles,
		districts,
		cx: buildings.length ? (lo + hi) / 2 : 0,
		cy: buildings.length ? (loY + hiY) / 2 : 0,
		dropped,
		codebaseSummary: graph.codebase_summary ?? "",
		databaseSummary: graph.database_summary ?? "",
	};
}

/**
 * An edge endpoint is either a storey, or the building itself. Nearly half the
 * edges in the one real graph measured point straight at a `db-table`, so the
 * second case is the common one and not a fallback: it anchors at the middle
 * storey and lights nothing, because nothing specific was named.
 */
function resolveEnd(
	id: string,
	storeyAt: Map<string, { b: Building; i: number }>,
	byId: Map<string, Building>,
): { b: Building; i: number; named: boolean } | null {
	const s = storeyAt.get(id);
	if (s) return { b: s.b, i: s.i, named: true };
	const b = byId.get(id);
	if (b) return { b, i: Math.floor((b.h - 1) / 2), named: false };
	return null;
}

function dominantRel(strands: Strand[]): Rel {
	const count = new Map<Rel, number>();
	for (const t of strands) count.set(t.rel, (count.get(t.rel) ?? 0) + 1);
	let best: Rel = REL_ORDER[0];
	let n = -1;
	for (const rel of REL_ORDER) {
		const c = count.get(rel) ?? 0;
		if (c > n) {
			n = c;
			best = rel;
		}
	}
	return best;
}

const meanStorey = (xs: number[]): number =>
	Math.round(xs.reduce((s, v) => s + v, 0) / xs.length);

// ── packing ──────────────────────────────────────────────────────────────────

interface Box {
	cols: number;
	rows: number;
	extentX: number;
	extentY: number;
	minX: number;
	maxX: number;
}

/**
 * ceil(sqrt(n / ratio)) only picks the right column count for square blocks.
 * With mixed footprints, try every count and keep the one whose natural spread
 * lands closest to the target ratio — in log space, so being twice too deep
 * costs the same as being twice too wide.
 */
function packDistrict(
	members: Building[],
	gapX: number,
	gapY: number,
	nearIsRight: boolean,
): Box {
	const n = members.length;
	if (n === 0)
		return { cols: 0, rows: 0, extentX: 0, extentY: 0, minX: 0, maxX: 0 };
	const avgW = members.reduce((s, b) => s + b.w, 0) / n;
	const avgD = members.reduce((s, b) => s + b.d, 0) / n;
	let cols = 1;
	let best = Infinity;
	for (let c = 1; c <= n; c++) {
		const r = Math.ceil(n / c);
		const err = Math.abs(
			Math.log(
				(r * (avgD + gapY) - gapY) / (c * (avgW + gapX) - gapX) / FACE_RATIO,
			),
		);
		if (err < best - 1e-9) {
			best = err;
			cols = c;
		}
	}
	const rows = Math.ceil(n / cols);
	// busiest members take the column nearest the other district, so the heaviest
	// tethers are also the shortest ones
	const ordered = members.slice().sort((a, b) => b.fanIn - a.fanIn);
	const columns: Building[][] = [];
	for (let c = 0; c < cols; c++)
		columns.push(ordered.slice(c * rows, (c + 1) * rows));

	// Each column is only as wide as its own widest member, and every block is
	// flush with the edge facing the other district: the facing side stays a
	// clean line while the ragged edge falls to the back, where it reads as depth
	// rather than as sloppiness.
	const slot = columns.map((_, c) => (nearIsRight ? cols - 1 - c : c));
	const width = new Array<number>(cols);
	columns.forEach((cm, c) => {
		width[slot[c]] = Math.max(...cm.map((b) => b.w));
	});
	const left = new Array<number>(cols);
	let cursor = 0;
	for (let s = 0; s < cols; s++) {
		left[s] = cursor;
		cursor += width[s] + gapX;
	}
	const extentX = cursor - gapX;

	const maxD = Math.max(...members.map((b) => b.d));
	// the labels fix the shallow axis, so it is the FACING axis that stretches to
	// reach the target ratio rather than the shallow one closing in
	const pitchY =
		rows > 1
			? Math.max(maxD + gapY, (extentX * FACE_RATIO - maxD) / (rows - 1))
			: 0;
	columns.forEach((cm, c) => {
		cm.forEach((b, i) => {
			b.cx = nearIsRight
				? left[slot[c]] + width[slot[c]] - b.w / 2
				: left[slot[c]] + b.w / 2;
			b.cy = i * pitchY;
		});
	});
	return {
		cols,
		rows,
		extentX,
		extentY: (rows - 1) * pitchY + maxD,
		minX: 0,
		maxX: extentX,
	};
}

// ── what the scene needs from a drum ─────────────────────────────────────────

/** the solid standing behind a drum's pixels, which is not the drawn radius */
export const solidRadius = (b: Building): number => diskSolidRadius(b.r);

/** how many characters of a storey name a drum can carry before it wraps too far */
export const drumChars = (b: Building): number =>
	Math.floor((2 * 1.28 * b.r * ISO_X * Math.SQRT1_2) / (MONO_ADV * FLOOR_FONT));

/** and how many a slab can carry across its own face */
export const slabChars = (b: Building): number =>
	Math.floor((b.w * ISO_X - 2 * FLOOR_PAD) / (MONO_ADV * FLOOR_FONT));
