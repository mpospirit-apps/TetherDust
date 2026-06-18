/* Tether canvas v3 — ER cards, two lanes, expressive edges.
 *
 * Mixed-mode rendering:
 *   • SVG layer  → edges only (taperPath wave + direction pulses)
 *   • HTML layer → cards with rich rows (icons, type chips, hover, accessible)
 * Both layers share a single transform so pan/zoom move them in lockstep.
 *
 * Containers (code-file / db-table) are the only nodes in the d3-force
 * simulation; their child rows (code-symbol / db-column) are HTML <li>
 * elements inside the parent card and resolve to a precise (x,y) for
 * row-level edge anchoring.
 *
 * Reads window.TETHER_GRAPH_URL or `data-graph-url` on the <svg>.
 *
 * This file is the orchestrator — DOM refs and shared state live in
 * ./state.js, and the heavy lifting is split across constants/data-prep/
 * render/details/interaction modules.
 */

import { state } from './state.js';
import { KIND_LABEL } from './constants.js';
import { prepareData } from './data-prep.js';
import { renderCards, measureCards, initSimulation, loop } from './render.js';
import { setupInfoPanel } from './details.js';
import { bindToolbar } from './interaction.js';

fetch(state.graphUrl)
    .then(r => r.json())
    .then(graph => {
        if (!graph.nodes || graph.nodes.length === 0) {
            if (state.banner) {
                state.banner.hidden = false;
                state.banner.textContent = 'No graph yet — generation may still be running.';
            }
            return;
        }
        setupInfoPanel(graph);
        prepareData(graph);
        renderCards();
        measureCards();
        initSimulation();
        bindToolbar();
        requestAnimationFrame(loop);
    })
    .catch(err => {
        if (state.banner) {
            state.banner.hidden = false;
            state.banner.textContent = 'Failed to load graph: ' + err.message;
        }
    });

export const TETHER_KIND_LABEL = KIND_LABEL;
