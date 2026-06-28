// Tether canvas controller — a faithful port of the legacy static/js/tethers/*
// modules (state / data-prep / render / interaction / details), restructured as
// a single imperative factory driven by a React component. It owns the SVG +
// HTML-cards DOM inside `root` (the .tether-canvas-wrap element), runs a
// d3-force simulation over the container cards, and renders animated tapered
// bezier edges in lockstep via a shared transform. `createTetherCanvas` returns
// a destroy function that stops the loop, the simulation, and all listeners.

import * as d3 from "d3";
import { bezierPt, computeCP, taperPath } from "./bezier";
import {
	ALL_RELS,
	CARD_PADDING_Y,
	cssEscape,
	escapeHtml,
	GAP_KEY,
	getGap,
	getSpread,
	HEADER_HEIGHT,
	KIND_ICON,
	KIND_LABEL,
	MAX_CARD_W,
	MAX_INLINE_ROWS,
	MIN_CARD_W,
	PREVIEW_ROWS,
	REL_COLOR,
	ROW_HEIGHT,
	SPREAD_KEY,
	svgEl,
} from "./constants";
import type { GraphEdge, GraphNode, TetherGraph } from "./types";

interface RuntimeNode extends GraphNode, d3.SimulationNodeDatum {
	x: number;
	y: number;
	fx?: number | null;
	fy?: number | null;
	_side?: "code" | "db";
	_kids?: RuntimeNode[];
	_visibleRows?: RuntimeNode[];
	_expanded?: boolean;
	_w: number;
	_h: number;
	_radius?: number;
}

interface RuntimeEdge extends GraphEdge {
	id: string;
	_sourceContainer?: string | null;
	_targetContainer?: string | null;
}

type Selection =
	| { kind: "node"; ref: RuntimeNode }
	| { kind: "edge"; ref: RuntimeEdge }
	| null;

interface RowIndex {
	containerId: string;
	rowIndex: number | null;
}

function asEl(target: EventTarget | null): Element | null {
	return target instanceof Element ? target : null;
}

export function createTetherCanvas(
	root: HTMLElement,
	graph: TetherGraph,
): () => void {
	const ac = new AbortController();
	const { signal } = ac;
	let rafId = 0;
	let panRafId = 0;

	const svg = root.querySelector<SVGSVGElement>("#tether-canvas");
	const cardsLayerEl = root.querySelector<HTMLElement>(".tether-cards-layer");
	if (!svg || !cardsLayerEl) return () => ac.abort();
	// Bind to an explicitly non-null type so it stays non-null inside every
	// nested closure below (control-flow narrowing of a const is not preserved
	// across all closure boundaries).
	const cardsLayer: HTMLElement = cardsLayerEl;

	const tooltip = root.querySelector<HTMLElement>("#tether-tooltip");
	const panel = root.querySelector<HTMLElement>("#tether-details-panel");
	const infoPanel = root.querySelector<HTMLElement>("#tether-info-panel");
	const searchInput = root.querySelector<HTMLInputElement>(
		".tether-search--popup",
	);
	const filterButtons = root.querySelectorAll<HTMLElement>(
		".tether-filters [data-rel]",
	);
	const fitBtn = root.querySelector<HTMLElement>(".tether-fitbtn");
	const spreadInput = root.querySelector<HTMLInputElement>(
		"#tether-spread-range",
	);
	const gapInput = root.querySelector<HTMLInputElement>("#tether-gap-range");

	const W = svg.clientWidth || 1100;
	const H = svg.clientHeight || 720;
	svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

	const _gap = getGap();

	const zoomLayer = svgEl("g", { class: "zoom-layer" });
	const edgesG = svgEl("g", { class: "edges" });
	const pulsesG = svgEl("g", { class: "pulses" });
	zoomLayer.appendChild(edgesG);
	zoomLayer.appendChild(pulsesG);
	svg.appendChild(zoomLayer);

	const state = {
		W,
		H,
		CODE_LANE_X: W * (0.5 - _gap),
		DB_LANE_X: W * (0.5 + _gap),
		SEAM_X: W * 0.5,
		SEAM_PAD: W * _gap * 0.25,

		allNodes: [] as RuntimeNode[],
		allEdges: [] as RuntimeEdge[],
		containers: [] as RuntimeNode[],
		nodesById: new Map<string, RuntimeNode>(),
		rowIndexById: new Map<string, RowIndex>(),
		edgesByContainerId: new Map<string, RuntimeEdge[]>(),
		edgesByEndpointId: new Map<string, RuntimeEdge[]>(),
		simulation: null as d3.Simulation<RuntimeNode, undefined> | null,
		phaseByEdge: new Map<string, number>(),
		speedByEdge: new Map<string, number>(),

		scale: 1,
		panX: 0,
		panY: 0,
		targetScale: 1,
		targetPanX: 0,
		targetPanY: 0,
		panning: false,
		initialLayoutFit: false,
		refitOnSettle: false,
		dragging: false,
		dragStart: null as { x: number; y: number } | null,

		selected: null as Selection,
		focusIds: null as Set<string> | null,
		activeRels: new Set<string>(ALL_RELS),
		searchTerm: "",

		tipTimer: 0,
	};

	// ── data-prep ───────────────────────────────────────────────────────────

	function sortChildren(kids: RuntimeNode[]): void {
		kids.sort((a, b) => {
			if (a.kind === "db-column" && b.kind === "db-column") {
				const ap = a.primary_key ? 0 : a.foreign_key ? 1 : 2;
				const bp = b.primary_key ? 0 : b.foreign_key ? 1 : 2;
				if (ap !== bp) return ap - bp;
			}
			return (a.label || "").localeCompare(b.label || "");
		});
	}

	function resolveContainer(nodeId: string | undefined): string | null {
		if (!nodeId) return null;
		const n = state.nodesById.get(nodeId);
		if (!n) return null;
		if (n.kind === "code-file" || n.kind === "db-table") return n.id;
		return n.parent_id || null;
	}

	function prepareData(g: TetherGraph): void {
		state.allNodes = g.nodes.map(
			(n) => ({ ...n, x: 0, y: 0, _w: MIN_CARD_W, _h: 0 }) as RuntimeNode,
		);
		state.allEdges = g.edges.map(
			(e, i) => ({ ...e, id: `e${i}` }) as RuntimeEdge,
		);
		state.nodesById = new Map(state.allNodes.map((n) => [n.id, n]));

		state.edgesByEndpointId = new Map();
		for (const e of state.allEdges) {
			for (const id of [e.source_id, e.target_id]) {
				let list = state.edgesByEndpointId.get(id);
				if (!list) {
					list = [];
					state.edgesByEndpointId.set(id, list);
				}
				list.push(e);
			}
			state.phaseByEdge.set(e.id, Math.random() * Math.PI * 2);
			state.speedByEdge.set(e.id, 0.4 + Math.random() * 0.6);
		}

		const childrenByParent = new Map<string, RuntimeNode[]>();
		for (const n of state.allNodes) {
			if (n.parent_id) {
				let kids = childrenByParent.get(n.parent_id);
				if (!kids) {
					kids = [];
					childrenByParent.set(n.parent_id, kids);
				}
				kids.push(n);
			}
		}
		state.containers = state.allNodes
			.filter((n) => n.kind === "code-file" || n.kind === "db-table")
			.map((n) => {
				const kids = (childrenByParent.get(n.id) || []).slice();
				sortChildren(kids);
				const expanded = kids.length <= MAX_INLINE_ROWS;
				const visibleRows = expanded ? kids : kids.slice(0, PREVIEW_ROWS);
				n._side = n.kind === "code-file" ? "code" : "db";
				n._kids = kids;
				n._visibleRows = visibleRows;
				n._expanded = expanded;
				n._w = MIN_CARD_W;
				n._h =
					HEADER_HEIGHT +
					Math.max(1, visibleRows.length) * ROW_HEIGHT +
					(kids.length > visibleRows.length ? ROW_HEIGHT : 0) +
					CARD_PADDING_Y * 2;
				n.x =
					(n._side === "code" ? state.CODE_LANE_X : state.DB_LANE_X) +
					(Math.random() - 0.5) * 60;
				n.y =
					(state.H + 52) / 2 + (Math.random() - 0.5) * ((state.H - 52) * 0.6);
				return n;
			});

		state.rowIndexById = new Map();
		for (const c of state.containers) {
			(c._visibleRows ?? []).forEach((row, idx) => {
				state.rowIndexById.set(row.id, { containerId: c.id, rowIndex: idx });
			});
			for (const k of c._kids ?? []) {
				if (!state.rowIndexById.has(k.id)) {
					state.rowIndexById.set(k.id, { containerId: c.id, rowIndex: null });
				}
			}
		}

		state.edgesByContainerId = new Map();
		for (const e of state.allEdges) {
			e._sourceContainer = resolveContainer(e.source_id);
			e._targetContainer = resolveContainer(e.target_id);
			for (const cid of [e._sourceContainer, e._targetContainer]) {
				if (!cid) continue;
				let list = state.edgesByContainerId.get(cid);
				if (!list) {
					list = [];
					state.edgesByContainerId.set(cid, list);
				}
				list.push(e);
			}
		}
	}

	// ── HTML cards ──────────────────────────────────────────────────────────

	function chip(text: string, cls: string): HTMLElement {
		const s = document.createElement("span");
		s.className = cls;
		s.textContent = text;
		return s;
	}

	function buildRowEl(_c: RuntimeNode, row: RuntimeNode): HTMLElement {
		const li = document.createElement("li");
		li.className = `trow trow--${row.kind}`;
		li.dataset.rowId = row.id;
		if (row.kind === "db-column" && row.primary_key)
			li.classList.add("trow--pk");
		if (row.kind === "db-column" && row.foreign_key)
			li.classList.add("trow--fk");

		const icon = document.createElement("span");
		icon.className = "trow__icon";
		if (row.kind === "db-column") {
			if (row.primary_key) icon.innerHTML = '<i class="fa-solid fa-key"></i>';
			else if (row.foreign_key) icon.textContent = "↗";
			else icon.textContent = "◇";
		} else {
			icon.textContent = "ƒ";
		}
		li.appendChild(icon);

		const name = document.createElement("span");
		name.className = "trow__name";
		name.textContent = row.label;
		li.appendChild(name);

		if (row.kind === "db-column" && row.data_type) {
			li.appendChild(chip(row.data_type, "trow__type"));
		} else if (row.kind === "code-symbol" && row.language) {
			li.appendChild(chip(row.language, "trow__type"));
		}

		li.addEventListener("click", (ev) => {
			ev.stopPropagation();
			select({ kind: "node", ref: row });
		});
		li.addEventListener("mouseenter", (ev) => showTip(ev, row));
		li.addEventListener("mouseleave", hideTip);
		return li;
	}

	function buildCardEl(c: RuntimeNode): HTMLElement {
		const art = document.createElement("article");
		art.className = `tcard tcard--${c.kind}`;
		art.dataset.nodeId = c.id;
		art.style.left = "0px";
		art.style.top = "0px";
		art.style.minWidth = `${MIN_CARD_W}px`;
		art.style.maxWidth = `${MAX_CARD_W}px`;

		const header = document.createElement("header");
		header.className = "tcard__header";
		const ic = document.createElement("i");
		ic.className = `fa-solid ${KIND_ICON[c.kind] || "fa-circle"}`;
		header.appendChild(ic);
		const title = document.createElement("span");
		title.className = "tcard__title";
		title.textContent = c.label;
		header.appendChild(title);
		if (c.kind === "db-table" && c.schema)
			header.appendChild(chip(c.schema, "tcard__chip"));
		if (c.kind === "code-file" && c.language)
			header.appendChild(chip(c.language, "tcard__chip"));
		header.addEventListener("click", (ev) => {
			ev.stopPropagation();
			select({ kind: "node", ref: c });
		});
		header.addEventListener("mouseenter", (ev) => showTip(ev, c));
		header.addEventListener("mouseleave", hideTip);
		attachCardDrag(header, c);
		art.appendChild(header);

		const ul = document.createElement("ul");
		ul.className = "tcard__rows";
		const kids = c._kids ?? [];
		const visibleRows = c._visibleRows ?? [];
		for (const row of visibleRows) ul.appendChild(buildRowEl(c, row));
		if (!c._expanded && kids.length > visibleRows.length) {
			const more = document.createElement("li");
			more.className = "trow trow--more";
			more.textContent = `▾  +${kids.length - visibleRows.length} more`;
			more.addEventListener("click", (ev) => {
				ev.stopPropagation();
				expandCard(c);
			});
			ul.appendChild(more);
		}
		art.appendChild(ul);
		return art;
	}

	function renderCards(): void {
		cardsLayer.innerHTML = "";
		for (const c of state.containers) cardsLayer.appendChild(buildCardEl(c));
	}

	function expandCard(c: RuntimeNode): void {
		c._expanded = true;
		c._visibleRows = (c._kids ?? []).slice();
		for (let i = 0; i < c._visibleRows.length; i++) {
			state.rowIndexById.set(c._visibleRows[i].id, {
				containerId: c.id,
				rowIndex: i,
			});
		}
		const el = cardsLayer.querySelector(`[data-node-id="${cssEscape(c.id)}"]`);
		if (el) el.replaceWith(buildCardEl(c));
		measureCard(c);
		if (state.simulation) state.simulation.alpha(0.6).restart();
	}

	function measureCard(c: RuntimeNode): void {
		const el = cardsLayer.querySelector(`[data-node-id="${cssEscape(c.id)}"]`);
		if (!el) return;
		const rect = el.getBoundingClientRect();
		c._w = rect.width;
		c._h = rect.height;
		c._radius = Math.max(c._w, c._h) / 2 + 14;
	}

	function measureCards(): void {
		for (const c of state.containers) measureCard(c);
	}

	// ── force simulation ────────────────────────────────────────────────────

	function positionCards(): void {
		for (const c of state.containers) {
			const el = cardsLayer.querySelector<HTMLElement>(
				`[data-node-id="${cssEscape(c.id)}"]`,
			);
			if (!el) continue;
			el.style.left = `${c.x - c._w / 2}px`;
			el.style.top = `${c.y - c._h / 2}px`;
		}
	}

	function initSimulation(): void {
		const containerIds = new Set(state.containers.map((c) => c.id));
		const linkData: d3.SimulationLinkDatum<RuntimeNode>[] = [];
		for (const e of state.allEdges) {
			const s = e._sourceContainer;
			const t = e._targetContainer;
			if (!s || !t || s === t) continue;
			if (!containerIds.has(s) || !containerIds.has(t)) continue;
			linkData.push({ source: s, target: t });
		}

		state.simulation = d3
			.forceSimulation<RuntimeNode>(state.containers)
			.force(
				"link",
				d3
					.forceLink<RuntimeNode, d3.SimulationLinkDatum<RuntimeNode>>(linkData)
					.id((d) => d.id)
					.distance(280)
					.strength(0.08)
					.iterations(2),
			)
			.force("charge", d3.forceManyBody<RuntimeNode>().strength(-getSpread()))
			.force(
				"xLane",
				d3
					.forceX<RuntimeNode>((d) =>
						d._side === "code" ? state.CODE_LANE_X : state.DB_LANE_X,
					)
					.strength(0.1),
			)
			.force("y", d3.forceY<RuntimeNode>((state.H + 52) / 2).strength(0.02))
			.force(
				"collide",
				d3
					.forceCollide<RuntimeNode>((d) => d._radius || 100)
					.strength(0.9)
					.iterations(2),
			)
			.alpha(1)
			.alphaDecay(0.04);

		state.simulation.on("tick", () => {
			for (const c of state.containers) {
				const halfW = c._w / 2;
				if (c._side === "code") {
					const maxX = state.SEAM_X - halfW - state.SEAM_PAD;
					if (c.x > maxX) c.x = maxX;
				} else {
					const minX = state.SEAM_X + halfW + state.SEAM_PAD;
					if (c.x < minX) c.x = minX;
				}
				if (c.fx != null) c.fx = c.x;
				if (c.fy != null) c.fy = c.y;
			}
			positionCards();
		});

		state.simulation.on("end", () => {
			if (!state.initialLayoutFit) {
				state.initialLayoutFit = true;
				zoomToFit();
			} else if (state.refitOnSettle) {
				state.refitOnSettle = false;
				zoomToFit();
			}
		});

		positionCards();
	}

	// ── edge anchoring ──────────────────────────────────────────────────────

	function cardSideAnchor(c: RuntimeNode): { x: number; y: number } {
		const innerSide = c._side === "code" ? +1 : -1;
		return { x: c.x + innerSide * (c._w / 2), y: c.y };
	}

	function rowAnchor(nodeId: string): { x: number; y: number } | null {
		const info = state.rowIndexById.get(nodeId);
		if (!info) {
			const container = state.nodesById.get(nodeId);
			if (
				container &&
				(container.kind === "code-file" || container.kind === "db-table")
			) {
				return cardSideAnchor(container);
			}
			return null;
		}
		const c = state.nodesById.get(info.containerId);
		if (!c) return null;
		if (info.rowIndex == null) return cardSideAnchor(c);
		const innerSide = c._side === "code" ? +1 : -1;
		const x = c.x + innerSide * (c._w / 2);
		const yTop = c.y - c._h / 2 + HEADER_HEIGHT + CARD_PADDING_Y;
		const y = yTop + (info.rowIndex + 0.5) * ROW_HEIGHT;
		return { x, y };
	}

	// ── edge rendering ──────────────────────────────────────────────────────

	function renderEdges(): void {
		edgesG.innerHTML = "";
		pulsesG.innerHTML = "";
		for (const e of state.allEdges) {
			const path = svgEl("path", {
				class: `tether-edge tether-edge--${e.relationship}`,
				fill: REL_COLOR[e.relationship] || "var(--c-cyan)",
				"data-edge-id": e.id,
			});
			(path as SVGElement).style.cursor = "pointer";
			path.addEventListener("click", (ev) => {
				ev.stopPropagation();
				select({ kind: "edge", ref: e });
			});
			path.addEventListener("mouseenter", (ev) => showTip(ev as MouseEvent, e));
			path.addEventListener("mouseleave", hideTip);
			edgesG.appendChild(path);

			const pulse = svgEl("circle", {
				class: `tether-pulse tether-pulse--${e.relationship}`,
				r: "3.5",
				fill: REL_COLOR[e.relationship] || "var(--c-cyan)",
				"data-edge-id": e.id,
			});
			pulsesG.appendChild(pulse);
		}
	}

	function filterEdges(): Set<string> {
		const ids = new Set<string>();
		for (const e of state.allEdges)
			if (state.activeRels.has(e.relationship)) ids.add(e.id);
		return ids;
	}

	function isDimmed(e: RuntimeEdge): boolean {
		if (!state.activeRels.has(e.relationship)) return true;
		if (
			state.focusIds &&
			!(state.focusIds.has(e.source_id) || state.focusIds.has(e.target_id))
		)
			return true;
		if (state.searchTerm) {
			const sNode = state.nodesById.get(e.source_id);
			const tNode = state.nodesById.get(e.target_id);
			const haystack = `${sNode?.label || ""} ${tNode?.label || ""}`;
			if (!haystack.toLowerCase().includes(state.searchTerm)) return true;
		}
		return false;
	}

	function applyCardDimming(): void {
		for (const c of state.containers) {
			const el = cardsLayer.querySelector(
				`[data-node-id="${cssEscape(c.id)}"]`,
			);
			if (!el) continue;
			let dim = false;
			if (state.focusIds && !state.focusIds.has(c.id)) {
				const focusIds = state.focusIds;
				const anyChildFocused = (c._kids || []).some((k) => focusIds.has(k.id));
				if (!anyChildFocused) dim = true;
			}
			if (state.searchTerm) {
				const hay = (
					c.label +
					" " +
					(c._kids || []).map((k) => k.label).join(" ")
				).toLowerCase();
				if (!hay.includes(state.searchTerm)) dim = true;
			}
			el.classList.toggle("is-dimmed", dim);
		}
	}

	function loop(ts: number): void {
		rafId = requestAnimationFrame(loop);
		if (!cardsLayer.children.length) return;
		if (!edgesG.children.length) renderEdges();

		const t = ts / 1000;
		const visibleEdges = filterEdges();
		const pathEls = edgesG.children;
		const pulseEls = pulsesG.children;

		for (let i = 0; i < pathEls.length; i++) {
			const e = state.allEdges[i];
			const visible = visibleEdges.has(e.id);
			const pathEl = pathEls[i] as SVGElement;
			const pulseEl = pulseEls[i] as SVGElement;
			if (!visible) {
				pathEl.setAttribute("d", "");
				pulseEl.setAttribute("cx", "-9999");
				continue;
			}

			const a = rowAnchor(e.source_id);
			const b = rowAnchor(e.target_id);
			if (!a || !b) {
				pathEl.setAttribute("d", "");
				pulseEl.setAttribute("cx", "-9999");
				continue;
			}

			const conf =
				typeof e.confidence === "number"
					? Math.max(0, Math.min(1, e.confidence))
					: 0.6;
			const maxW = 3 + conf * 8;
			const phase = state.phaseByEdge.get(e.id) || 0;
			const speed = state.speedByEdge.get(e.id) || 1;
			const cp =
				computeCP(a.x, a.y, b.x, b.y, t, phase, speed, 0.1, 30) ||
				({ cpx: (a.x + b.x) / 2, cpy: (a.y + b.y) / 2 } as const);

			pathEl.setAttribute(
				"d",
				taperPath(a.x, a.y, b.x, b.y, cp.cpx, cp.cpy, maxW),
			);

			const pt = (t * 0.65 + (state.phaseByEdge.get(e.id) || 0)) % 1;
			const p = bezierPt(a.x, a.y, b.x, b.y, cp.cpx, cp.cpy, pt);
			pulseEl.setAttribute("cx", String(p.x));
			pulseEl.setAttribute("cy", String(p.y));

			const dim = isDimmed(e);
			pathEl.style.opacity = dim ? "0.08" : "0.85";
			pulseEl.style.opacity = dim ? "0" : "1";
		}

		applyCardDimming();
	}

	// ── tooltips ────────────────────────────────────────────────────────────

	function firstSentence(t: string): string {
		if (!t) return "";
		const m = t.match(/^[^.!?]+[.!?]/);
		return m ? m[0].trim() : t.length > 120 ? `${t.slice(0, 117)}…` : t;
	}

	function showTip(ev: MouseEvent, target: RuntimeNode | RuntimeEdge): void {
		if (!tooltip) return;
		window.clearTimeout(state.tipTimer);
		state.tipTimer = window.setTimeout(() => {
			const fragments: string[] = [];
			if ("relationship" in target && target.relationship) {
				const sNode = state.nodesById.get(target.source_id);
				const tNode = state.nodesById.get(target.target_id);
				fragments.push(`<strong>${target.relationship}</strong>`);
				fragments.push(`${sNode?.label ?? "?"} → ${tNode?.label ?? "?"}`);
				if (target.description)
					fragments.push(
						`<span class="tether-tooltip__desc">${escapeHtml(firstSentence(target.description))}</span>`,
					);
			} else if ("kind" in target) {
				const ic = KIND_ICON[target.kind];
				fragments.push(
					`<span>${ic ? `<i class="fa-solid ${ic}"></i> ` : ""}<strong>${escapeHtml(target.label)}</strong></span>`,
				);
				fragments.push(
					`<span class="tether-tooltip__kind">${KIND_LABEL[target.kind] || target.kind}</span>`,
				);
				if (target.description)
					fragments.push(
						`<span class="tether-tooltip__desc">${escapeHtml(firstSentence(target.description))}</span>`,
					);
				else if (target.data_type)
					fragments.push(
						`<span class="tether-tooltip__desc">${target.data_type}</span>`,
					);
				else if (target.signature)
					fragments.push(
						`<span class="tether-tooltip__desc">${escapeHtml(target.signature)}</span>`,
					);
			}
			tooltip.innerHTML = fragments.join("<br>");
			const r = root.getBoundingClientRect();
			tooltip.style.left = `${ev.clientX - r.left + 12}px`;
			tooltip.style.top = `${ev.clientY - r.top + 12}px`;
			tooltip.classList.add("is-visible");
		}, 180);
	}

	function hideTip(): void {
		window.clearTimeout(state.tipTimer);
		if (tooltip) tooltip.classList.remove("is-visible");
	}

	// ── selection / details panel ───────────────────────────────────────────

	function refreshHighlights(): void {
		cardsLayer.querySelectorAll(".tcard").forEach((el) => {
			el.classList.remove("is-selected");
		});
		cardsLayer.querySelectorAll(".trow").forEach((el) => {
			el.classList.remove("is-selected");
		});
		edgesG.querySelectorAll(".tether-edge").forEach((el) => {
			el.classList.remove("is-selected");
		});
		if (!state.selected) return;
		if (state.selected.kind === "node") {
			const n = state.selected.ref;
			if (n.kind === "code-file" || n.kind === "db-table") {
				const el = cardsLayer.querySelector(
					`.tcard[data-node-id="${cssEscape(n.id)}"]`,
				);
				if (el) el.classList.add("is-selected");
			} else {
				const el = cardsLayer.querySelector(
					`.trow[data-row-id="${cssEscape(n.id)}"]`,
				);
				if (el) el.classList.add("is-selected");
			}
		} else {
			const el = edgesG.querySelector(
				`.tether-edge[data-edge-id="${cssEscape(state.selected.ref.id)}"]`,
			);
			if (el) el.classList.add("is-selected");
		}
	}

	function select(sel: NonNullable<Selection>): void {
		state.selected = sel;
		if (sel.kind === "node") {
			const n = sel.ref;
			const oneHop = new Set<string>([n.id]);
			const followEdges = (nodeId: string) => {
				for (const e of state.edgesByEndpointId.get(nodeId) || []) {
					oneHop.add(e.source_id);
					oneHop.add(e.target_id);
					const sn = state.nodesById.get(e.source_id);
					const tn = state.nodesById.get(e.target_id);
					if (sn?.parent_id) oneHop.add(sn.parent_id);
					if (tn?.parent_id) oneHop.add(tn.parent_id);
				}
			};
			followEdges(n.id);
			if (n.kind === "code-file" || n.kind === "db-table") {
				for (const k of n._kids || []) {
					oneHop.add(k.id);
					followEdges(k.id);
				}
			} else if (n.parent_id) {
				oneHop.add(n.parent_id);
			}
			state.focusIds = oneHop;
			if (panel) renderNodeDetails(n);
		} else {
			const e = sel.ref;
			state.focusIds = new Set([e.source_id, e.target_id]);
			const sn = state.nodesById.get(e.source_id);
			const tn = state.nodesById.get(e.target_id);
			if (sn?.parent_id) state.focusIds.add(sn.parent_id);
			if (tn?.parent_id) state.focusIds.add(tn.parent_id);
			if (panel) renderEdgeDetails(e);
		}
		refreshHighlights();
		centerOnFocused();
	}

	function clearSelection(): void {
		state.selected = null;
		state.focusIds = null;
		if (panel) {
			panel.classList.remove("is-open");
			panel.innerHTML = "";
		}
		refreshHighlights();
	}

	function panelHeader(
		eyebrow: string,
		title: string,
		accent?: string,
	): HTMLElement {
		const h = document.createElement("div");
		h.className = "tether-panel__header";
		if (accent) h.style.borderLeft = `3px solid ${accent}`;
		const e = document.createElement("div");
		e.className = "tether-panel__eyebrow";
		e.textContent = eyebrow;
		const t = document.createElement("h3");
		t.className = "tether-panel__title";
		t.textContent = title;
		h.appendChild(e);
		h.appendChild(t);
		return h;
	}

	function pEl(text: string): HTMLElement {
		const el = document.createElement("p");
		el.className = "tether-panel__desc";
		el.textContent = text;
		return el;
	}

	function metaList(rows: [string, string][]): HTMLElement {
		const dl = document.createElement("dl");
		dl.className = "tether-panel__meta";
		for (const [k, v] of rows) {
			const dt = document.createElement("dt");
			dt.textContent = k;
			const dd = document.createElement("dd");
			dd.textContent = v;
			dl.appendChild(dt);
			dl.appendChild(dd);
		}
		return dl;
	}

	function codeBlock(text: string, lang: string, heading: string): HTMLElement {
		const wrap = document.createElement("div");
		wrap.className = "tether-panel__code";
		if (heading) {
			const h = document.createElement("h4");
			h.textContent = `${heading}${lang ? ` · ${lang}` : ""}`;
			wrap.appendChild(h);
		}
		const pre = document.createElement("pre");
		pre.className = `tether-panel__pre lang-${(lang || "text").toLowerCase()}`;
		pre.textContent = text;
		wrap.appendChild(pre);
		return wrap;
	}

	function edgesList(nodeId: string, edges: RuntimeEdge[]): HTMLElement {
		const wrap = document.createElement("div");
		wrap.className = "tether-panel__edges";
		const heading = document.createElement("h4");
		heading.textContent = "Connections";
		wrap.appendChild(heading);
		const ul = document.createElement("ul");
		ul.className = "tether-panel__list";
		for (const e of edges) {
			const otherId = e.source_id === nodeId ? e.target_id : e.source_id;
			const other = state.nodesById.get(otherId);
			const li = document.createElement("li");
			const pill = document.createElement("span");
			pill.className = `tether-panel__pill tether-panel__pill--${e.relationship}`;
			pill.style.background = REL_COLOR[e.relationship] || "var(--c-cyan)";
			pill.textContent = e.relationship;
			const link = document.createElement("button");
			link.className = "tether-panel__link";
			link.textContent = other ? other.label : otherId;
			link.addEventListener("click", () => select({ kind: "edge", ref: e }));
			li.appendChild(pill);
			li.appendChild(link);
			ul.appendChild(li);
		}
		wrap.appendChild(ul);
		return wrap;
	}

	function paintPanel(parts: HTMLElement[]): void {
		if (!panel) return;
		panel.innerHTML = "";
		panel.classList.add("is-open");
		const close = document.createElement("button");
		close.className = "tether-panel__close";
		close.setAttribute("aria-label", "Close details");
		close.innerHTML = "&times;";
		close.addEventListener("click", clearSelection);
		panel.appendChild(close);
		for (const part of parts) panel.appendChild(part);
	}

	function renderNodeDetails(n: RuntimeNode): void {
		const parts: HTMLElement[] = [];
		parts.push(panelHeader(KIND_LABEL[n.kind] || n.kind, n.label));
		if (n.description) parts.push(pEl(n.description));
		const meta: [string, string][] = [];
		if (n.kind === "code-file" && n.path) meta.push(["Path", n.path]);
		if (n.language) meta.push(["Language", n.language]);
		if (n.kind === "code-symbol" && n.signature)
			meta.push(["Signature", n.signature]);
		if (n.kind === "code-symbol" && n.line_range)
			meta.push(["Lines", String(n.line_range)]);
		if (n.kind === "db-table" && n.schema) meta.push(["Schema", n.schema]);
		if (n.kind === "db-table" && n.row_count_hint)
			meta.push(["Row count", n.row_count_hint]);
		if (n.kind === "db-column" && n.data_type) meta.push(["Type", n.data_type]);
		if (n.kind === "db-column") {
			if (n.primary_key) meta.push(["Key", "PRIMARY"]);
			if (n.foreign_key) meta.push(["Foreign key", n.foreign_key]);
			if (n.nullable === false) meta.push(["Nullable", "NO"]);
		}
		if (meta.length) parts.push(metaList(meta));
		if (n.snippet)
			parts.push(codeBlock(n.snippet, n.language || "text", "Snippet"));
		const touching = state.edgesByEndpointId.get(n.id) || [];
		if (touching.length) parts.push(edgesList(n.id, touching));
		paintPanel(parts);
	}

	function renderEdgeDetails(e: RuntimeEdge): void {
		const sNode = state.nodesById.get(e.source_id);
		const tNode = state.nodesById.get(e.target_id);
		const parts: HTMLElement[] = [];
		parts.push(
			panelHeader(
				`Relationship: ${e.relationship}`,
				`${sNode ? sNode.label : e.source_id} → ${tNode ? tNode.label : e.target_id}`,
				REL_COLOR[e.relationship],
			),
		);
		if (e.description) parts.push(pEl(e.description));
		const meta: [string, string][] = [];
		if (typeof e.confidence === "number")
			meta.push(["Confidence", e.confidence.toFixed(2)]);
		if (sNode)
			meta.push(["Source", `${KIND_LABEL[sNode.kind]} · ${sNode.label}`]);
		if (tNode)
			meta.push(["Target", `${KIND_LABEL[tNode.kind]} · ${tNode.label}`]);
		parts.push(metaList(meta));
		const snippet = e.evidence_snippet || e.evidence;
		if (snippet)
			parts.push(codeBlock(snippet, e.evidence_lang || "text", "Evidence"));
		paintPanel(parts);
	}

	// ── info panel (code + database summaries) ──────────────────────────────

	function buildInfoSection(label: string, body: string): HTMLElement {
		const div = document.createElement("div");
		div.className = "tether-info-panel__section";
		const lbl = document.createElement("div");
		lbl.className = "tether-info-panel__label";
		lbl.textContent = label;
		const p = document.createElement("p");
		p.className = "tether-info-panel__body";
		p.textContent = body;
		div.appendChild(lbl);
		div.appendChild(p);
		return div;
	}

	function setupInfoPanel(g: TetherGraph): void {
		if (!infoPanel) return;
		infoPanel.innerHTML = "";
		const hasSummary = g.codebase_summary || g.database_summary;
		if (!hasSummary) {
			const btn = root.querySelector<HTMLElement>("#tether-info-toggle");
			if (btn) btn.style.display = "none";
			return;
		}
		if (g.codebase_summary)
			infoPanel.appendChild(buildInfoSection("Code", g.codebase_summary));
		if (g.database_summary)
			infoPanel.appendChild(buildInfoSection("Database", g.database_summary));
	}

	// ── card drag ───────────────────────────────────────────────────────────

	function attachCardDrag(handle: HTMLElement, c: RuntimeNode): void {
		handle.style.cursor = "grab";
		handle.addEventListener("mousedown", (ev) => {
			if (ev.button !== 0) return;
			ev.preventDefault();
			ev.stopPropagation();
			const rect = root.getBoundingClientRect();
			const startWx = (ev.clientX - rect.left - state.panX) / state.scale;
			const startWy = (ev.clientY - rect.top - state.panY) / state.scale;
			const startNx = c.x;
			const startNy = c.y;
			let moved = false;
			handle.style.cursor = "grabbing";
			c.fx = c.x;
			c.fy = c.y;
			if (state.simulation) state.simulation.alphaTarget(0.3).restart();

			const dragAc = new AbortController();
			function onMove(e: MouseEvent) {
				const wx = (e.clientX - rect.left - state.panX) / state.scale;
				const wy = (e.clientY - rect.top - state.panY) / state.scale;
				const dx = wx - startWx;
				const dy = wy - startWy;
				if (!moved && Math.hypot(dx, dy) < 4) return;
				moved = true;
				c.fx = startNx + dx;
				c.fy = startNy + dy;
			}
			function onUp() {
				dragAc.abort();
				handle.style.cursor = "grab";
				if (state.simulation) state.simulation.alphaTarget(0);
				if (!moved) {
					c.fx = null;
					c.fy = null;
				}
			}
			window.addEventListener("mousemove", onMove, { signal: dragAc.signal });
			window.addEventListener("mouseup", onUp, { signal: dragAc.signal });
			signal.addEventListener("abort", () => dragAc.abort());
		});

		handle.addEventListener("dblclick", (ev) => {
			ev.stopPropagation();
			c.fx = null;
			c.fy = null;
			if (state.simulation) state.simulation.alpha(0.5).restart();
		});
	}

	// ── smooth pan/zoom animation ───────────────────────────────────────────

	function applyTransform(): void {
		const t = `translate(${state.panX}px, ${state.panY}px) scale(${state.scale})`;
		cardsLayer.style.transform = t;
		zoomLayer.setAttribute(
			"transform",
			`translate(${state.panX}, ${state.panY}) scale(${state.scale})`,
		);
	}

	function animateStep(): void {
		const k = 0.14;
		state.panX += (state.targetPanX - state.panX) * k;
		state.panY += (state.targetPanY - state.panY) * k;
		state.scale += (state.targetScale - state.scale) * k;
		applyTransform();
		if (
			Math.abs(state.targetPanX - state.panX) < 0.15 &&
			Math.abs(state.targetPanY - state.panY) < 0.15 &&
			Math.abs(state.targetScale - state.scale) < 0.0008
		) {
			state.panX = state.targetPanX;
			state.panY = state.targetPanY;
			state.scale = state.targetScale;
			applyTransform();
			state.panning = false;
		} else {
			panRafId = requestAnimationFrame(animateStep);
		}
	}

	function animateTo(tx: number, ty: number, ts: number): void {
		state.targetPanX = tx;
		state.targetPanY = ty;
		state.targetScale = ts;
		if (!state.panning) {
			state.panning = true;
			panRafId = requestAnimationFrame(animateStep);
		}
	}

	function usableW(): number {
		const panelOpen = panel?.classList.contains("is-open");
		const panelW = panelOpen ? panel?.offsetWidth || 420 : 0;
		return state.W - panelW;
	}

	function zoomToFit(): void {
		if (!state.containers.length) return;
		let minX = Infinity,
			minY = Infinity,
			maxX = -Infinity,
			maxY = -Infinity;
		for (const c of state.containers) {
			minX = Math.min(minX, c.x - c._w / 2);
			minY = Math.min(minY, c.y - c._h / 2);
			maxX = Math.max(maxX, c.x + c._w / 2);
			maxY = Math.max(maxY, c.y + c._h / 2);
		}
		const padding = 60;
		const uw = usableW();
		const bbW = maxX - minX + padding * 2;
		const bbH = maxY - minY + padding * 2;
		if (!Number.isFinite(bbW) || bbW <= 0) return;
		const newScale = Math.min(uw / bbW, state.H / bbH, 1.4);
		const cx = (minX + maxX) / 2;
		const cy = (minY + maxY) / 2;
		animateTo(uw / 2 - cx * newScale, state.H / 2 - cy * newScale, newScale);
	}

	function centerOnFocused(): void {
		if (!state.focusIds?.size) return;
		const focusIds = state.focusIds;
		const focused = state.containers.filter(
			(c) =>
				focusIds.has(c.id) || (c._kids || []).some((k) => focusIds.has(k.id)),
		);
		if (!focused.length) return;
		let minX = Infinity,
			minY = Infinity,
			maxX = -Infinity,
			maxY = -Infinity;
		for (const c of focused) {
			minX = Math.min(minX, c.x - c._w / 2);
			minY = Math.min(minY, c.y - c._h / 2);
			maxX = Math.max(maxX, c.x + c._w / 2);
			maxY = Math.max(maxY, c.y + c._h / 2);
		}
		if (!Number.isFinite(minX)) return;
		const padding = 80;
		const uw = usableW();
		const bbW = maxX - minX + padding * 2;
		const bbH = maxY - minY + padding * 2;
		const newScale = Math.min(uw / bbW, state.H / bbH, 1.6);
		const cx = (minX + maxX) / 2;
		const cy = (minY + maxY) / 2;
		animateTo(uw / 2 - cx * newScale, state.H / 2 - cy * newScale, newScale);
	}

	// ── toolbar (search / filters / fit / spread / gap / info) ──────────────

	function bindToolbar(): void {
		if (searchInput) {
			searchInput.addEventListener("input", () => {
				state.searchTerm = (searchInput.value || "").toLowerCase().trim();
			});
		}
		filterButtons.forEach((btn) => {
			btn.addEventListener("click", () => {
				const rel = btn.dataset.rel as string;
				if (state.activeRels.has(rel)) {
					state.activeRels.delete(rel);
					btn.classList.remove("is-on");
				} else {
					state.activeRels.add(rel);
					btn.classList.add("is-on");
				}
			});
		});
		if (fitBtn) fitBtn.addEventListener("click", () => zoomToFit());

		const searchToggle = root.querySelector<HTMLElement>(
			"#tether-search-toggle",
		);
		const filterToggle = root.querySelector<HTMLElement>(
			"#tether-filter-toggle",
		);
		const filterPanel = root.querySelector<HTMLElement>("#tether-filter-panel");
		const infoToggle = root.querySelector<HTMLElement>("#tether-info-toggle");

		if (infoToggle && infoPanel) {
			infoToggle.addEventListener("click", () => {
				const opening = infoPanel.hidden;
				infoPanel.hidden = !opening;
				infoToggle.classList.toggle("is-active", opening);
			});
		}
		if (searchToggle && searchInput) {
			searchToggle.addEventListener("click", () => {
				const opening = searchInput.hidden;
				searchInput.hidden = !opening;
				searchToggle.classList.toggle("is-active", opening);
				searchInput.value = "";
				state.searchTerm = "";
				if (opening) searchInput.focus();
			});
		}
		if (filterToggle && filterPanel) {
			filterToggle.addEventListener("click", () => {
				const opening = filterPanel.hidden;
				filterPanel.hidden = !opening;
				filterToggle.classList.toggle("is-active", opening);
			});
		}

		const spreadToggle = root.querySelector<HTMLElement>(
			"#tether-spread-toggle",
		);
		const spreadPanel = root.querySelector<HTMLElement>("#tether-spread-panel");
		if (spreadToggle && spreadPanel) {
			spreadToggle.addEventListener("click", () => {
				const opening = spreadPanel.hidden;
				spreadPanel.hidden = !opening;
				spreadToggle.classList.toggle("is-active", opening);
			});
		}
		if (spreadInput) {
			spreadInput.value = String(getSpread());
			spreadInput.addEventListener("input", () => {
				const v = Number(spreadInput.value);
				if (!Number.isFinite(v) || v <= 0) return;
				localStorage.setItem(SPREAD_KEY, String(v));
				const sim = state.simulation;
				const charge = sim?.force("charge") as
					| d3.ForceManyBody<RuntimeNode>
					| undefined;
				if (charge && sim) {
					charge.strength(-v);
					state.refitOnSettle = true;
					sim.alpha(0.5).restart();
				}
			});
		}
		if (gapInput) {
			gapInput.value = String(getGap());
			gapInput.addEventListener("input", () => {
				const g = Number(gapInput.value);
				if (!Number.isFinite(g) || g <= 0) return;
				localStorage.setItem(GAP_KEY, String(g));
				state.CODE_LANE_X = state.W * (0.5 - g);
				state.DB_LANE_X = state.W * (0.5 + g);
				state.SEAM_PAD = state.W * g * 0.25;
				const sim = state.simulation;
				const xForce = sim?.force("xLane") as
					| d3.ForceX<RuntimeNode>
					| undefined;
				if (xForce && sim) {
					sim.force("xLane", xForce);
					state.refitOnSettle = true;
					sim.alpha(0.5).restart();
				}
			});
		}
	}

	// ── pan / zoom (wrap + window listeners) ────────────────────────────────

	function isChrome(target: Element | null): boolean {
		return !!(
			target?.closest(".tcard") ||
			target?.closest(".tether-edge") ||
			target?.closest(".tether-panel") ||
			target?.closest(".tether-toolbar") ||
			target?.closest(".tether-controls")
		);
	}

	root.addEventListener(
		"wheel",
		(ev) => {
			ev.preventDefault();
			const rect = root.getBoundingClientRect();
			const cx = ev.clientX - rect.left;
			const cy = ev.clientY - rect.top;
			const delta = ev.deltaY > 0 ? 0.9 : 1.1;
			const newScale = Math.max(0.2, Math.min(4, state.scale * delta));
			if (newScale === state.scale) return;
			state.panX = cx - (cx - state.panX) * (newScale / state.scale);
			state.panY = cy - (cy - state.panY) * (newScale / state.scale);
			state.scale = newScale;
			state.targetPanX = state.panX;
			state.targetPanY = state.panY;
			state.targetScale = state.scale;
			applyTransform();
		},
		{ passive: false, signal },
	);

	root.addEventListener(
		"mousedown",
		(ev) => {
			if (isChrome(asEl(ev.target))) return;
			state.panning = false;
			state.targetPanX = state.panX;
			state.targetPanY = state.panY;
			state.targetScale = state.scale;
			state.dragging = true;
			state.dragStart = {
				x: ev.clientX - state.panX,
				y: ev.clientY - state.panY,
			};
		},
		{ signal },
	);

	window.addEventListener(
		"mousemove",
		(ev) => {
			if (!state.dragging || !state.dragStart) return;
			state.panX = ev.clientX - state.dragStart.x;
			state.panY = ev.clientY - state.dragStart.y;
			state.targetPanX = state.panX;
			state.targetPanY = state.panY;
			applyTransform();
		},
		{ signal },
	);

	window.addEventListener(
		"mouseup",
		() => {
			state.dragging = false;
		},
		{ signal },
	);

	root.addEventListener(
		"click",
		(ev) => {
			if (isChrome(asEl(ev.target))) return;
			clearSelection();
		},
		{ signal },
	);

	// ── boot ────────────────────────────────────────────────────────────────

	setupInfoPanel(graph);
	prepareData(graph);
	renderCards();
	measureCards();
	initSimulation();
	bindToolbar();
	rafId = requestAnimationFrame(loop);

	return () => {
		ac.abort();
		cancelAnimationFrame(rafId);
		cancelAnimationFrame(panRafId);
		state.simulation?.stop();
	};
}
