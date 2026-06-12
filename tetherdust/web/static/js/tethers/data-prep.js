// Graph parsing — populate state.allNodes/allEdges/containers/nodesById/etc.
// from the raw JSON returned by the graphUrl fetch.

import { state } from './state.js';
import {
    HEADER_HEIGHT, ROW_HEIGHT, CARD_PADDING_Y,
    MAX_INLINE_ROWS, PREVIEW_ROWS, MIN_CARD_W,
} from './constants.js';

export function prepareData(graph) {
    state.allNodes = graph.nodes.map(n => ({ ...n }));
    state.allEdges = graph.edges.map((e, i) => ({ ...e, id: `e${i}` }));
    state.nodesById = new Map(state.allNodes.map(n => [n.id, n]));

    state.edgesByEndpointId = new Map();
    for (const e of state.allEdges) {
        for (const id of [e.source_id, e.target_id]) {
            if (!state.edgesByEndpointId.has(id)) state.edgesByEndpointId.set(id, []);
            state.edgesByEndpointId.get(id).push(e);
        }
        state.phaseByEdge.set(e.id, Math.random() * Math.PI * 2);
        state.speedByEdge.set(e.id, 0.4 + Math.random() * 0.6);
    }

    // Containers: code-file + db-table. Children are sorted and stashed.
    const childrenByParent = new Map();
    for (const n of state.allNodes) {
        if (n.parent_id) {
            if (!childrenByParent.has(n.parent_id)) childrenByParent.set(n.parent_id, []);
            childrenByParent.get(n.parent_id).push(n);
        }
    }
    state.containers = state.allNodes
        .filter(n => n.kind === 'code-file' || n.kind === 'db-table')
        .map(n => {
            const kids = (childrenByParent.get(n.id) || []).slice();
            sortChildren(kids);
            const expanded = kids.length <= MAX_INLINE_ROWS;
            const visibleRows = expanded ? kids : kids.slice(0, PREVIEW_ROWS);
            n._side = n.kind === 'code-file' ? 'code' : 'db';
            n._kids = kids;
            n._visibleRows = visibleRows;
            n._expanded = expanded;
            n._w = MIN_CARD_W;
            n._h = HEADER_HEIGHT + Math.max(1, visibleRows.length) * ROW_HEIGHT
                 + (kids.length > visibleRows.length ? ROW_HEIGHT : 0)
                 + CARD_PADDING_Y * 2;
            // seed positions inside the right lane so the first tick doesn't
            // throw cards across the seam
            n.x = (n._side === 'code' ? state.CODE_LANE_X : state.DB_LANE_X)
                + (Math.random() - 0.5) * 60;
            n.y = (state.H + 52) / 2 + (Math.random() - 0.5) * ((state.H - 52) * 0.6);
            return n;
        });

    // Index rows so edges can resolve to a precise (x,y).
    state.rowIndexById = new Map();
    for (const c of state.containers) {
        c._visibleRows.forEach((row, idx) => {
            state.rowIndexById.set(row.id, { containerId: c.id, rowIndex: idx });
        });
        // also entries for hidden children — they resolve to "card edge, center"
        for (const k of c._kids) {
            if (!state.rowIndexById.has(k.id)) {
                state.rowIndexById.set(k.id, { containerId: c.id, rowIndex: null });
            }
        }
    }

    // Resolve every edge endpoint to a containerId and record it.
    state.edgesByContainerId = new Map();
    for (const e of state.allEdges) {
        e._sourceContainer = resolveContainer(e.source_id);
        e._targetContainer = resolveContainer(e.target_id);
        for (const cid of [e._sourceContainer, e._targetContainer]) {
            if (!cid) continue;
            if (!state.edgesByContainerId.has(cid)) state.edgesByContainerId.set(cid, []);
            state.edgesByContainerId.get(cid).push(e);
        }
    }
}

export function sortChildren(kids) {
    kids.sort((a, b) => {
        if (a.kind === 'db-column' && b.kind === 'db-column') {
            const ap = a.primary_key ? 0 : (a.foreign_key ? 1 : 2);
            const bp = b.primary_key ? 0 : (b.foreign_key ? 1 : 2);
            if (ap !== bp) return ap - bp;
        }
        return (a.label || '').localeCompare(b.label || '');
    });
}

export function resolveContainer(nodeId) {
    if (!nodeId) return null;
    const n = state.nodesById.get(nodeId);
    if (!n) return null;
    if (n.kind === 'code-file' || n.kind === 'db-table') return n.id;
    return n.parent_id || null;
}
