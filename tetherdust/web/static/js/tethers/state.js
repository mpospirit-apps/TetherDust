// Single shared mutable state object for the tether canvas. Initialises DOM
// references and the SVG scaffold at module-load time so anything importing
// `state` sees a fully-formed object.

import { ALL_RELS, svgEl, getGap } from './constants.js';

const svg = document.getElementById('tether-canvas');
if (!svg) throw new Error('#tether-canvas not found');

const wrap = svg.parentElement;
const cardsLayer = wrap.querySelector('.tether-cards-layer');
const tooltip = document.getElementById('tether-tooltip');
const panel = document.getElementById('tether-details-panel');
const infoPanel = document.getElementById('tether-info-panel');
const searchInput = wrap.querySelector('.tether-search--popup');
const filterButtons = wrap.querySelectorAll('.tether-filters [data-rel]');
const fitBtn = wrap.querySelector('.tether-fitbtn');
const spreadInput = wrap.querySelector('#tether-spread-range');
const gapInput = wrap.querySelector('#tether-gap-range');
const banner = document.getElementById('tether-status-banner');

const graphUrl = svg.dataset.graphUrl || window.TETHER_GRAPH_URL;
if (!graphUrl) throw new Error('No graph URL on canvas');

const W = svg.clientWidth || 1100;
const H = svg.clientHeight || 720;
svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

const SEAM_X = W * 0.5;
const _gap = getGap();
const CODE_LANE_X = W * (0.5 - _gap);
const DB_LANE_X = W * (0.5 + _gap);
const SEAM_PAD = W * _gap * 0.25;   // minimum half-wall enforced at the seam

// SVG scaffold: zoom layer holds edges + pulses; both layers move in lockstep
// with the cards layer via a shared transform.
const zoomLayer = svgEl('g', { class: 'zoom-layer' });
const edgesG = svgEl('g', { class: 'edges' });
const pulsesG = svgEl('g', { class: 'pulses' });
zoomLayer.appendChild(edgesG);
zoomLayer.appendChild(pulsesG);
svg.appendChild(zoomLayer);

export const state = {
    // ── DOM refs ──────────────────────────────────────────────────────
    svg, wrap, cardsLayer, tooltip, panel, infoPanel,
    searchInput, filterButtons, fitBtn, spreadInput, gapInput, banner,
    graphUrl,

    // ── Layout (immutable post-init) ──────────────────────────────────
    W, H, CODE_LANE_X, DB_LANE_X, SEAM_X, SEAM_PAD,

    // ── SVG scaffold ──────────────────────────────────────────────────
    zoomLayer, edgesG, pulsesG,

    // ── Graph state ───────────────────────────────────────────────────
    allNodes: [],
    allEdges: [],
    containers: [],
    nodesById: new Map(),
    rowIndexById: new Map(),         // childId -> { containerId, rowIndex }
    edgesByContainerId: new Map(),
    edgesByEndpointId: new Map(),
    simulation: null,
    phaseByEdge: new Map(),
    speedByEdge: new Map(),

    // ── View state ────────────────────────────────────────────────────
    scale: 1, panX: 0, panY: 0,
    targetScale: 1, targetPanX: 0, targetPanY: 0,
    panning: false,                  // true while a programmatic anim is running
    initialLayoutFit: false,         // guards initial zoomToFit
    refitOnSettle: false,            // re-fit once after a spread change settles
    dragging: false, dragStart: null,

    // ── Selection / focus ─────────────────────────────────────────────
    selected: null,
    focusIds: null,                  // Set of nodeIds in 1-hop neighborhood
    activeRels: new Set(ALL_RELS),
    searchTerm: '',

    // ── Tooltip ───────────────────────────────────────────────────────
    tipTimer: null,
};
