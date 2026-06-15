// Card rendering, force simulation, edge geometry, and the per-frame
// animation loop. Reads/writes state.* directly. Selection and tooltip side
// effects come from sibling modules (details / interaction) — those imports
// form a cycle but are only resolved at runtime, which ES modules tolerate.

import * as d3 from 'https://cdn.jsdelivr.net/npm/d3-force@3/+esm';
import { taperPath, bezierPt, computeCP } from './tether-bezier.js';
import { state } from './state.js';
import {
    KIND_ICON, REL_COLOR,
    HEADER_HEIGHT, ROW_HEIGHT, CARD_PADDING_Y,
    MIN_CARD_W, MAX_CARD_W,
    getSpread,
    svgEl, cssEscape,
} from './constants.js';
import { select } from './details.js';
import { attachCardDrag, showTip, hideTip, zoomToFit } from './interaction.js';

/* ───────────── HTML cards ───────────── */

export function renderCards() {
    state.cardsLayer.innerHTML = '';
    for (const c of state.containers) {
        state.cardsLayer.appendChild(buildCardEl(c));
    }
}

function buildCardEl(c) {
    const art = document.createElement('article');
    art.className = `tcard tcard--${c.kind}`;
    art.dataset.nodeId = c.id;
    art.style.left = '0px';
    art.style.top = '0px';
    art.style.minWidth = MIN_CARD_W + 'px';
    art.style.maxWidth = MAX_CARD_W + 'px';

    const header = document.createElement('header');
    header.className = 'tcard__header';
    const ic = document.createElement('i');
    ic.className = `fa-solid ${KIND_ICON[c.kind] || 'fa-circle'}`;
    header.appendChild(ic);
    const title = document.createElement('span');
    title.className = 'tcard__title';
    title.textContent = c.label;
    header.appendChild(title);
    if (c.kind === 'db-table' && c.schema) {
        header.appendChild(chip(c.schema, 'tcard__chip'));
    }
    if (c.kind === 'code-file' && c.language) {
        header.appendChild(chip(c.language, 'tcard__chip'));
    }
    header.addEventListener('click', (ev) => {
        ev.stopPropagation();
        select({ kind: 'node', ref: c });
    });
    header.addEventListener('mouseenter', (ev) => showTip(ev, c));
    header.addEventListener('mouseleave', hideTip);
    attachCardDrag(header, c);
    art.appendChild(header);

    const ul = document.createElement('ul');
    ul.className = 'tcard__rows';
    for (const row of c._visibleRows) {
        ul.appendChild(buildRowEl(c, row));
    }
    if (!c._expanded && c._kids.length > c._visibleRows.length) {
        const more = document.createElement('li');
        more.className = 'trow trow--more';
        more.textContent = `▾  +${c._kids.length - c._visibleRows.length} more`;
        more.addEventListener('click', (ev) => {
            ev.stopPropagation();
            expandCard(c);
        });
        ul.appendChild(more);
    }
    art.appendChild(ul);
    return art;
}

function buildRowEl(c, row) {
    const li = document.createElement('li');
    li.className = `trow trow--${row.kind}`;
    li.dataset.rowId = row.id;

    if (row.kind === 'db-column' && row.primary_key) li.classList.add('trow--pk');
    if (row.kind === 'db-column' && row.foreign_key) li.classList.add('trow--fk');

    const icon = document.createElement('span');
    icon.className = 'trow__icon';
    if (row.kind === 'db-column') {
        if (row.primary_key) icon.innerHTML = '<i class="fa-solid fa-key"></i>';
        else if (row.foreign_key) icon.textContent = '↗';
        else icon.textContent = '◇';
    } else {
        icon.textContent = 'ƒ';
    }
    li.appendChild(icon);

    const name = document.createElement('span');
    name.className = 'trow__name';
    name.textContent = row.label;
    li.appendChild(name);

    if (row.kind === 'db-column' && row.data_type) {
        li.appendChild(chip(row.data_type, 'trow__type'));
    } else if (row.kind === 'code-symbol' && row.language) {
        li.appendChild(chip(row.language, 'trow__type'));
    }

    li.addEventListener('click', (ev) => {
        ev.stopPropagation();
        select({ kind: 'node', ref: row });
    });
    li.addEventListener('mouseenter', (ev) => showTip(ev, row));
    li.addEventListener('mouseleave', hideTip);
    return li;
}

function chip(text, cls) {
    const s = document.createElement('span');
    s.className = cls;
    s.textContent = text;
    return s;
}

function expandCard(c) {
    c._expanded = true;
    c._visibleRows = c._kids.slice();
    // re-index rows for new visible set (now all kids are visible)
    for (let i = 0; i < c._visibleRows.length; i++) {
        state.rowIndexById.set(c._visibleRows[i].id, { containerId: c.id, rowIndex: i });
    }
    // replace just this card's DOM in place
    const el = state.cardsLayer.querySelector(`[data-node-id="${cssEscape(c.id)}"]`);
    if (el) el.replaceWith(buildCardEl(c));
    measureCard(c);
    if (state.simulation) state.simulation.alpha(0.6).restart();
}

export function measureCards() {
    for (const c of state.containers) measureCard(c);
}

function measureCard(c) {
    const el = state.cardsLayer.querySelector(`[data-node-id="${cssEscape(c.id)}"]`);
    if (!el) return;
    const rect = el.getBoundingClientRect();
    c._w = rect.width;
    c._h = rect.height;
    c._radius = Math.max(c._w, c._h) / 2 + 14;
}

/* ───────────── force simulation ───────────── */

export function initSimulation() {
    // Build a clean link dataset for d3.forceLink. We do NOT mutate allEdges:
    // edge rendering uses raw source_id/target_id via rowAnchor() so we can
    // anchor to specific column/symbol rows. The simulation only cares about
    // container-to-container connections for layout.
    const containerIds = new Set(state.containers.map(c => c.id));
    const linkData = [];
    for (const e of state.allEdges) {
        const s = e._sourceContainer;
        const t = e._targetContainer;
        if (!s || !t || s === t) continue;
        if (!containerIds.has(s) || !containerIds.has(t)) continue;
        linkData.push({ source: s, target: t });
    }

    state.simulation = d3.forceSimulation(state.containers)
        .force('link', d3.forceLink(linkData)
            .id(d => d.id)
            .distance(280)
            .strength(0.08)
            .iterations(2)
        )
        .force('charge', d3.forceManyBody().strength(-getSpread()))
        .force('xLane', d3.forceX(d =>
            d._side === 'code' ? state.CODE_LANE_X : state.DB_LANE_X
        ).strength(0.10))
        .force('y', d3.forceY((state.H + 52) / 2).strength(0.02))
        .force('collide', d3.forceCollide(d => d._radius || 100).strength(0.9).iterations(2))
        .alpha(1).alphaDecay(0.04);

    state.simulation.on('tick', () => {
        for (const c of state.containers) {
            // Only constraint: keep each lane on its own side of the seam so
            // code and db cards never intermix. Otherwise let cards spread
            // freely beyond the viewport — zoomToFit frames the result, and the
            // spread slider can actually push cards apart instead of jamming
            // them against the viewport walls.
            const halfW = c._w / 2;
            if (c._side === 'code') {
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

    state.simulation.on('end', () => {
        if (!state.initialLayoutFit) { state.initialLayoutFit = true; zoomToFit(); }
        else if (state.refitOnSettle) { state.refitOnSettle = false; zoomToFit(); }
    });

    // Position cards once with their seeded coords so nothing renders at (0,0)
    // before the first tick lands.
    positionCards();
}

function positionCards() {
    for (const c of state.containers) {
        const el = state.cardsLayer.querySelector(`[data-node-id="${cssEscape(c.id)}"]`);
        if (!el) continue;
        el.style.left = (c.x - c._w / 2) + 'px';
        el.style.top = (c.y - c._h / 2) + 'px';
    }
}

/* ───────────── edge anchoring ───────────── */

export function rowAnchor(nodeId) {
    const info = state.rowIndexById.get(nodeId);
    if (!info) {
        // Maybe it IS a container (code-file / db-table) — anchor at side edge
        const container = state.nodesById.get(nodeId);
        if (container && (container.kind === 'code-file' || container.kind === 'db-table')) {
            return cardSideAnchor(container);
        }
        return null;
    }
    const c = state.nodesById.get(info.containerId);
    if (!c) return null;
    if (info.rowIndex == null) return cardSideAnchor(c);
    const innerSide = c._side === 'code' ? +1 : -1;     // exit on inner side
    const x = c.x + innerSide * (c._w / 2);
    const yTop = c.y - c._h / 2 + HEADER_HEIGHT + CARD_PADDING_Y;
    const y = yTop + (info.rowIndex + 0.5) * ROW_HEIGHT;
    return { x, y };
}

function cardSideAnchor(c) {
    const innerSide = c._side === 'code' ? +1 : -1;
    return { x: c.x + innerSide * (c._w / 2), y: c.y };
}

/* ───────────── edge rendering ───────────── */

function renderEdges() {
    state.edgesG.innerHTML = '';
    state.pulsesG.innerHTML = '';
    for (const e of state.allEdges) {
        const path = svgEl('path', {
            'class': `tether-edge tether-edge--${e.relationship}`,
            'fill': REL_COLOR[e.relationship] || 'var(--c-cyan)',
            'data-edge-id': e.id,
        });
        path.style.cursor = 'pointer';
        path.addEventListener('click', (ev) => {
            ev.stopPropagation();
            select({ kind: 'edge', ref: e });
        });
        path.addEventListener('mouseenter', (ev) => showTip(ev, e));
        path.addEventListener('mouseleave', hideTip);
        state.edgesG.appendChild(path);

        const pulse = svgEl('circle', {
            'class': `tether-pulse tether-pulse--${e.relationship}`,
            'r': 3.5,
            'fill': REL_COLOR[e.relationship] || 'var(--c-cyan)',
            'data-edge-id': e.id,
        });
        state.pulsesG.appendChild(pulse);
    }
}

/* ───────────── frame loop (animation + edge geometry) ───────────── */

export function loop(ts) {
    if (!state.cardsLayer.children.length) return;
    if (!state.edgesG.children.length) renderEdges();

    const t = ts / 1000;
    const visibleEdges = filterEdges();

    const pathEls = state.edgesG.children;
    const pulseEls = state.pulsesG.children;

    for (let i = 0; i < pathEls.length; i++) {
        const e = state.allEdges[i];
        const visible = visibleEdges.has(e.id);
        const pathEl = pathEls[i];
        const pulseEl = pulseEls[i];
        if (!visible) {
            pathEl.setAttribute('d', '');
            pulseEl.setAttribute('cx', '-9999');
            continue;
        }

        const a = rowAnchor(e.source_id);
        const b = rowAnchor(e.target_id);
        if (!a || !b) {
            pathEl.setAttribute('d', '');
            pulseEl.setAttribute('cx', '-9999');
            continue;
        }

        // Confidence → thickness (3 .. 11)
        const conf = (typeof e.confidence === 'number') ? Math.max(0, Math.min(1, e.confidence)) : 0.6;
        const maxW = 3 + conf * 8;

        // Oscillating control point preserves the brand wave aesthetic
        const phase = state.phaseByEdge.get(e.id) || 0;
        const speed = state.speedByEdge.get(e.id) || 1;
        const cp = computeCP(a.x, a.y, b.x, b.y, t, phase, speed, 0.10, 30) ||
            { cpx: (a.x + b.x) / 2, cpy: (a.y + b.y) / 2 };

        pathEl.setAttribute('d', taperPath(a.x, a.y, b.x, b.y, cp.cpx, cp.cpy, maxW));

        // Pulse position along the curve
        const pt = ((t * 0.65 + (state.phaseByEdge.get(e.id) || 0)) % 1);
        const p = bezierPt(a.x, a.y, b.x, b.y, cp.cpx, cp.cpy, pt);
        pulseEl.setAttribute('cx', p.x);
        pulseEl.setAttribute('cy', p.y);

        // Focus + filter dimming
        const dim = isDimmed(e);
        pathEl.style.opacity = dim ? '0.08' : '0.85';
        pulseEl.style.opacity = dim ? '0' : '1';
    }

    // Card opacity for search/focus
    applyCardDimming();

    requestAnimationFrame(loop);
}

function filterEdges() {
    // Apply relationship filter only — focus + search are visual dim, not removal,
    // so the geometry still renders.
    const ids = new Set();
    for (const e of state.allEdges) {
        if (state.activeRels.has(e.relationship)) ids.add(e.id);
    }
    return ids;
}

function isDimmed(e) {
    if (!state.activeRels.has(e.relationship)) return true;
    if (state.focusIds && !(state.focusIds.has(e.source_id) || state.focusIds.has(e.target_id))) return true;
    if (state.searchTerm) {
        const sNode = state.nodesById.get(e.source_id);
        const tNode = state.nodesById.get(e.target_id);
        const haystack = (sNode?.label || '') + ' ' + (tNode?.label || '');
        if (!haystack.toLowerCase().includes(state.searchTerm)) return true;
    }
    return false;
}

function applyCardDimming() {
    for (const c of state.containers) {
        const el = state.cardsLayer.querySelector(`[data-node-id="${cssEscape(c.id)}"]`);
        if (!el) continue;
        let dim = false;
        if (state.focusIds && !state.focusIds.has(c.id)) {
            const anyChildFocused = (c._kids || []).some(k => state.focusIds.has(k.id));
            if (!anyChildFocused) dim = true;
        }
        if (state.searchTerm) {
            const hay = (c.label + ' ' +
                (c._kids || []).map(k => k.label).join(' ')).toLowerCase();
            if (!hay.includes(state.searchTerm)) dim = true;
        }
        el.classList.toggle('is-dimmed', dim);
    }
}
