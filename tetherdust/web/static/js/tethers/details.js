// Selection logic + side details panel + info panel.
// `select` is the central entry point for both node and edge clicks; it also
// drives the focus highlighting and pans the camera to centre the selection.

import { state } from './state.js';
import { KIND_LABEL, REL_COLOR, cssEscape } from './constants.js';
import { centerOnFocused } from './interaction.js';

/* ───────────── selection / focus ───────────── */

export function select(sel) {
    state.selected = sel;
    if (sel.kind === 'node') {
        const n = sel.ref;
        const oneHop = new Set([n.id]);
        // Walk edges from a node and pull in endpoints + their parent containers.
        const followEdges = (nodeId) => {
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
        if (n.kind === 'code-file' || n.kind === 'db-table') {
            // Also traverse edges from every child row so connected containers light up.
            for (const k of n._kids || []) { oneHop.add(k.id); followEdges(k.id); }
        } else if (n.parent_id) {
            oneHop.add(n.parent_id);
        }
        state.focusIds = oneHop;
        if (state.panel) renderNodeDetails(n);
    } else if (sel.kind === 'edge') {
        const e = sel.ref;
        state.focusIds = new Set([e.source_id, e.target_id]);
        const sn = state.nodesById.get(e.source_id);
        const tn = state.nodesById.get(e.target_id);
        if (sn?.parent_id) state.focusIds.add(sn.parent_id);
        if (tn?.parent_id) state.focusIds.add(tn.parent_id);
        if (state.panel) renderEdgeDetails(e);
    }
    refreshHighlights();
    centerOnFocused();
}

export function clearSelection() {
    state.selected = null;
    state.focusIds = null;
    if (state.panel) {
        state.panel.classList.remove('is-open');
        state.panel.innerHTML = '';
    }
    refreshHighlights();
}

export function refreshHighlights() {
    state.cardsLayer.querySelectorAll('.tcard').forEach(el => el.classList.remove('is-selected'));
    state.cardsLayer.querySelectorAll('.trow').forEach(el => el.classList.remove('is-selected'));
    state.edgesG.querySelectorAll('.tether-edge').forEach(el => el.classList.remove('is-selected'));
    if (!state.selected) return;
    if (state.selected.kind === 'node') {
        const n = state.selected.ref;
        if (n.kind === 'code-file' || n.kind === 'db-table') {
            const el = state.cardsLayer.querySelector(`.tcard[data-node-id="${cssEscape(n.id)}"]`);
            if (el) el.classList.add('is-selected');
        } else {
            const el = state.cardsLayer.querySelector(`.trow[data-row-id="${cssEscape(n.id)}"]`);
            if (el) el.classList.add('is-selected');
        }
    } else {
        const el = state.edgesG.querySelector(`.tether-edge[data-edge-id="${cssEscape(state.selected.ref.id)}"]`);
        if (el) el.classList.add('is-selected');
    }
}

/* ───────────── side panel ───────────── */

function renderNodeDetails(n) {
    const parts = [];
    parts.push(panelHeader(KIND_LABEL[n.kind] || n.kind, n.label));
    if (n.description) parts.push(p(n.description));
    const meta = [];
    if (n.kind === 'code-file' && n.path) meta.push(['Path', n.path]);
    if (n.language) meta.push(['Language', n.language]);
    if (n.kind === 'code-symbol' && n.signature) meta.push(['Signature', n.signature]);
    if (n.kind === 'code-symbol' && n.line_range) meta.push(['Lines', String(n.line_range)]);
    if (n.kind === 'db-table' && n.schema) meta.push(['Schema', n.schema]);
    if (n.kind === 'db-table' && n.row_count_hint) meta.push(['Row count', n.row_count_hint]);
    if (n.kind === 'db-column' && n.data_type) meta.push(['Type', n.data_type]);
    if (n.kind === 'db-column') {
        if (n.primary_key) meta.push(['Key', 'PRIMARY']);
        if (n.foreign_key) meta.push(['Foreign key', n.foreign_key]);
        if (n.nullable === false) meta.push(['Nullable', 'NO']);
    }
    if (meta.length) parts.push(metaList(meta));
    if (n.snippet) parts.push(codeBlock(n.snippet, n.language || 'text', 'Snippet'));

    const touching = (state.edgesByEndpointId.get(n.id) || []);
    if (touching.length) parts.push(edgesList(n.id, touching));

    paintPanel(parts);
}

function renderEdgeDetails(e) {
    const sNode = state.nodesById.get(e.source_id);
    const tNode = state.nodesById.get(e.target_id);
    const parts = [];
    parts.push(panelHeader(
        `Relationship: ${e.relationship}`,
        `${sNode ? sNode.label : e.source_id} → ${tNode ? tNode.label : e.target_id}`,
        REL_COLOR[e.relationship],
    ));
    if (e.description) parts.push(p(e.description));
    const meta = [];
    if (typeof e.confidence === 'number') meta.push(['Confidence', e.confidence.toFixed(2)]);
    if (sNode) meta.push(['Source', `${KIND_LABEL[sNode.kind]} · ${sNode.label}`]);
    if (tNode) meta.push(['Target', `${KIND_LABEL[tNode.kind]} · ${tNode.label}`]);
    parts.push(metaList(meta));
    const snippet = e.evidence_snippet || e.evidence;
    if (snippet) parts.push(codeBlock(snippet, e.evidence_lang || 'text', 'Evidence'));
    paintPanel(parts);
}

function paintPanel(parts) {
    state.panel.innerHTML = '';
    state.panel.classList.add('is-open');
    const close = document.createElement('button');
    close.className = 'tether-panel__close';
    close.setAttribute('aria-label', 'Close details');
    close.innerHTML = '&times;';
    close.addEventListener('click', clearSelection);
    state.panel.appendChild(close);
    for (const part of parts) state.panel.appendChild(part);
}

function panelHeader(eyebrow, title, accent) {
    const h = document.createElement('div');
    h.className = 'tether-panel__header';
    if (accent) h.style.borderLeft = `3px solid ${accent}`;
    const e = document.createElement('div');
    e.className = 'tether-panel__eyebrow';
    e.textContent = eyebrow;
    const t = document.createElement('h3');
    t.className = 'tether-panel__title';
    t.textContent = title;
    h.appendChild(e); h.appendChild(t);
    return h;
}

function p(text) {
    const el = document.createElement('p');
    el.className = 'tether-panel__desc';
    el.textContent = text;
    return el;
}

function metaList(rows) {
    const dl = document.createElement('dl');
    dl.className = 'tether-panel__meta';
    for (const [k, v] of rows) {
        const dt = document.createElement('dt'); dt.textContent = k;
        const dd = document.createElement('dd'); dd.textContent = v;
        dl.appendChild(dt); dl.appendChild(dd);
    }
    return dl;
}

function codeBlock(text, lang, heading) {
    const wrap = document.createElement('div');
    wrap.className = 'tether-panel__code';
    if (heading) {
        const h = document.createElement('h4');
        h.textContent = `${heading}${lang ? ` · ${lang}` : ''}`;
        wrap.appendChild(h);
    }
    const pre = document.createElement('pre');
    pre.className = `tether-panel__pre lang-${(lang || 'text').toLowerCase()}`;
    pre.textContent = text;
    wrap.appendChild(pre);
    return wrap;
}

function edgesList(nodeId, edges) {
    const wrap = document.createElement('div');
    wrap.className = 'tether-panel__edges';
    const heading = document.createElement('h4');
    heading.textContent = 'Connections';
    wrap.appendChild(heading);
    const ul = document.createElement('ul');
    ul.className = 'tether-panel__list';
    for (const e of edges) {
        const otherId = e.source_id === nodeId ? e.target_id : e.source_id;
        const other = state.nodesById.get(otherId);
        const li = document.createElement('li');
        const pill = document.createElement('span');
        pill.className = `tether-panel__pill tether-panel__pill--${e.relationship}`;
        pill.style.background = REL_COLOR[e.relationship] || 'var(--c-cyan)';
        pill.textContent = e.relationship;
        const link = document.createElement('button');
        link.className = 'tether-panel__link';
        link.textContent = other ? other.label : otherId;
        link.addEventListener('click', () => select({ kind: 'edge', ref: e }));
        li.appendChild(pill); li.appendChild(link);
        ul.appendChild(li);
    }
    wrap.appendChild(ul);
    return wrap;
}

/* ───────────── info panel (code + database summaries) ───────────── */

export function setupInfoPanel(graph) {
    if (!state.infoPanel) return;
    state.infoPanel.innerHTML = '';
    const hasSummary = graph.codebase_summary || graph.database_summary;
    if (!hasSummary) {
        const btn = state.wrap.querySelector('#tether-info-toggle');
        if (btn) btn.style.display = 'none';
        return;
    }
    if (graph.codebase_summary) state.infoPanel.appendChild(buildInfoSection('Code', graph.codebase_summary));
    if (graph.database_summary) state.infoPanel.appendChild(buildInfoSection('Database', graph.database_summary));
}

function buildInfoSection(label, body) {
    const div = document.createElement('div');
    div.className = 'tether-info-panel__section';
    const lbl = document.createElement('div');
    lbl.className = 'tether-info-panel__label';
    lbl.textContent = label;
    const p = document.createElement('p');
    p.className = 'tether-info-panel__body';
    p.textContent = body;
    div.appendChild(lbl);
    div.appendChild(p);
    return div;
}
