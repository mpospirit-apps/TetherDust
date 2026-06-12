// Toolbar wiring, card drag, pan/zoom, animation, tooltips.
// Module-level event listeners attach to state.wrap on import; they no-op
// until graph data lands and cards/edges are rendered.

import { state } from './state.js';
import { KIND_ICON, KIND_LABEL, escapeHtml, getSpread, SPREAD_KEY, getGap, GAP_KEY } from './constants.js';
import { clearSelection } from './details.js';

/* ───────────── tooltips ───────────── */

export function showTip(ev, target) {
    if (!state.tooltip) return;
    clearTimeout(state.tipTimer);
    state.tipTimer = setTimeout(() => {
        const fragments = [];
        if (target.relationship) {
            const sNode = state.nodesById.get(target.source_id);
            const tNode = state.nodesById.get(target.target_id);
            fragments.push(`<strong>${target.relationship}</strong>`);
            fragments.push(`${sNode?.label ?? '?'} → ${tNode?.label ?? '?'}`);
            if (target.description) fragments.push(`<span class="tether-tooltip__desc">${escapeHtml(firstSentence(target.description))}</span>`);
        } else {
            const ic = KIND_ICON[target.kind];
            fragments.push(`<span>${ic ? `<i class="fa-solid ${ic}"></i> ` : ''}<strong>${escapeHtml(target.label)}</strong></span>`);
            fragments.push(`<span class="tether-tooltip__kind">${KIND_LABEL[target.kind] || target.kind}</span>`);
            if (target.description) fragments.push(`<span class="tether-tooltip__desc">${escapeHtml(firstSentence(target.description))}</span>`);
            else if (target.data_type) fragments.push(`<span class="tether-tooltip__desc">${target.data_type}</span>`);
            else if (target.signature) fragments.push(`<span class="tether-tooltip__desc">${escapeHtml(target.signature)}</span>`);
        }
        state.tooltip.innerHTML = fragments.join('<br>');
        const r = state.wrap.getBoundingClientRect();
        const x = ev.clientX - r.left + 12;
        const y = ev.clientY - r.top + 12;
        state.tooltip.style.left = x + 'px';
        state.tooltip.style.top = y + 'px';
        state.tooltip.classList.add('is-visible');
    }, 180);
}

export function hideTip() {
    clearTimeout(state.tipTimer);
    if (state.tooltip) state.tooltip.classList.remove('is-visible');
}

function firstSentence(t) {
    if (!t) return '';
    const m = t.match(/^[^.!?]+[.!?]/);
    return m ? m[0].trim() : (t.length > 120 ? t.slice(0, 117) + '…' : t);
}

/* ───────────── toolbar (search / filters / fit) ───────────── */

export function bindToolbar() {
    if (state.searchInput) {
        state.searchInput.addEventListener('input', () => {
            state.searchTerm = (state.searchInput.value || '').toLowerCase().trim();
        });
    }
    state.filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const rel = btn.dataset.rel;
            if (state.activeRels.has(rel)) {
                state.activeRels.delete(rel);
                btn.classList.remove('is-on');
            } else {
                state.activeRels.add(rel);
                btn.classList.add('is-on');
            }
        });
    });
    if (state.fitBtn) state.fitBtn.addEventListener('click', () => zoomToFit());

    const searchToggle = state.wrap.querySelector('#tether-search-toggle');
    const filterToggle = state.wrap.querySelector('#tether-filter-toggle');
    const filterPanel = state.wrap.querySelector('#tether-filter-panel');
    const infoToggle = state.wrap.querySelector('#tether-info-toggle');

    if (infoToggle && state.infoPanel) {
        infoToggle.addEventListener('click', () => {
            const opening = state.infoPanel.hidden;
            state.infoPanel.hidden = !opening;
            infoToggle.classList.toggle('is-active', opening);
        });
    }

    if (searchToggle && state.searchInput) {
        searchToggle.addEventListener('click', () => {
            const opening = state.searchInput.hidden;
            state.searchInput.hidden = !opening;
            searchToggle.classList.toggle('is-active', opening);
            state.searchInput.value = '';
            state.searchTerm = '';
            if (opening) state.searchInput.focus();
        });
    }
    if (filterToggle && filterPanel) {
        filterToggle.addEventListener('click', () => {
            const opening = filterPanel.hidden;
            filterPanel.hidden = !opening;
            filterToggle.classList.toggle('is-active', opening);
        });
    }

    const spreadToggle = state.wrap.querySelector('#tether-spread-toggle');
    const spreadPanel = state.wrap.querySelector('#tether-spread-panel');
    if (spreadToggle && spreadPanel) {
        spreadToggle.addEventListener('click', () => {
            const opening = spreadPanel.hidden;
            spreadPanel.hidden = !opening;
            spreadToggle.classList.toggle('is-active', opening);
        });
    }
    if (state.spreadInput) {
        // Reflect the persisted value, then push live updates into the charge
        // force and gently reheat so cards re-settle at the new spacing.
        state.spreadInput.value = String(getSpread());
        state.spreadInput.addEventListener('input', () => {
            const v = Number(state.spreadInput.value);
            if (!Number.isFinite(v) || v <= 0) return;
            localStorage.setItem(SPREAD_KEY, String(v));
            const charge = state.simulation && state.simulation.force('charge');
            if (charge) {
                charge.strength(-v);
                state.refitOnSettle = true;
                state.simulation.alpha(0.5).restart();
            }
        });
    }
    if (state.gapInput) {
        // Gap moves the lane centers apart (and widens the seam wall), then
        // re-initialises the lane force so cards migrate to the new columns.
        state.gapInput.value = String(getGap());
        state.gapInput.addEventListener('input', () => {
            const g = Number(state.gapInput.value);
            if (!Number.isFinite(g) || g <= 0) return;
            localStorage.setItem(GAP_KEY, String(g));
            state.CODE_LANE_X = state.W * (0.5 - g);
            state.DB_LANE_X = state.W * (0.5 + g);
            state.SEAM_PAD = state.W * g * 0.25;
            const xForce = state.simulation && state.simulation.force('xLane');
            if (xForce) {
                // Re-registering the force re-runs its initialize step, which
                // re-reads the lane accessor against the updated state.
                state.simulation.force('xLane', xForce);
                state.refitOnSettle = true;
                state.simulation.alpha(0.5).restart();
            }
        });
    }
}

/* ───────────── card drag ───────────── */

export function attachCardDrag(handle, c) {
    handle.style.cursor = 'grab';
    handle.addEventListener('mousedown', (ev) => {
        if (ev.button !== 0) return;
        ev.preventDefault();
        ev.stopPropagation();
        const rect = state.wrap.getBoundingClientRect();
        const startWx = (ev.clientX - rect.left - state.panX) / state.scale;
        const startWy = (ev.clientY - rect.top - state.panY) / state.scale;
        const startNx = c.x;
        const startNy = c.y;
        let moved = false;
        handle.style.cursor = 'grabbing';
        c.fx = c.x;
        c.fy = c.y;
        if (state.simulation) state.simulation.alphaTarget(0.3).restart();

        function onMove(e) {
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
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
            handle.style.cursor = 'grab';
            if (state.simulation) state.simulation.alphaTarget(0);
            // If the user merely clicked (no movement), release the pin so the
            // node can settle naturally; otherwise leave it pinned where dropped.
            if (!moved) { c.fx = null; c.fy = null; }
        }
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
    });

    // Double-click the header to release a pinned node.
    handle.addEventListener('dblclick', (ev) => {
        ev.stopPropagation();
        c.fx = null;
        c.fy = null;
        if (state.simulation) state.simulation.alpha(0.5).restart();
    });
}

/* ───────────── smooth pan/zoom animation ───────────── */

function animateTo(tx, ty, ts) {
    state.targetPanX = tx;
    state.targetPanY = ty;
    state.targetScale = ts;
    if (!state.panning) { state.panning = true; requestAnimationFrame(animateStep); }
}

function animateStep() {
    const k = 0.14;
    state.panX += (state.targetPanX - state.panX) * k;
    state.panY += (state.targetPanY - state.panY) * k;
    state.scale += (state.targetScale - state.scale) * k;
    applyTransform();
    if (Math.abs(state.targetPanX - state.panX) < 0.15 &&
        Math.abs(state.targetPanY - state.panY) < 0.15 &&
        Math.abs(state.targetScale - state.scale) < 0.0008) {
        state.panX = state.targetPanX;
        state.panY = state.targetPanY;
        state.scale = state.targetScale;
        applyTransform();
        state.panning = false;
    } else {
        requestAnimationFrame(animateStep);
    }
}

// Returns visible width accounting for the open side panel.
function usableW() {
    const panelOpen = state.panel && state.panel.classList.contains('is-open');
    const panelW = panelOpen ? (state.panel.offsetWidth || 420) : 0;
    return state.W - panelW;
}

export function zoomToFit() {
    if (!state.containers.length) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const c of state.containers) {
        minX = Math.min(minX, c.x - c._w / 2);
        minY = Math.min(minY, c.y - c._h / 2);
        maxX = Math.max(maxX, c.x + c._w / 2);
        maxY = Math.max(maxY, c.y + c._h / 2);
    }
    const padding = 60;
    const uw = usableW();
    const bbW = (maxX - minX) + padding * 2;
    const bbH = (maxY - minY) + padding * 2;
    if (!Number.isFinite(bbW) || bbW <= 0) return;
    const newScale = Math.min(uw / bbW, state.H / bbH, 1.4);
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    animateTo(uw / 2 - cx * newScale, state.H / 2 - cy * newScale, newScale);
}

export function centerOnFocused() {
    if (!state.focusIds || !state.focusIds.size) return;
    const focused = state.containers.filter(c =>
        state.focusIds.has(c.id) || (c._kids || []).some(k => state.focusIds.has(k.id))
    );
    if (!focused.length) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const c of focused) {
        minX = Math.min(minX, c.x - c._w / 2);
        minY = Math.min(minY, c.y - c._h / 2);
        maxX = Math.max(maxX, c.x + c._w / 2);
        maxY = Math.max(maxY, c.y + c._h / 2);
    }
    if (!Number.isFinite(minX)) return;
    const padding = 80;
    const uw = usableW();
    const bbW = (maxX - minX) + padding * 2;
    const bbH = (maxY - minY) + padding * 2;
    const newScale = Math.min(uw / bbW, state.H / bbH, 1.6);
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    animateTo(uw / 2 - cx * newScale, state.H / 2 - cy * newScale, newScale);
}

function applyTransform() {
    const t = `translate(${state.panX}px, ${state.panY}px) scale(${state.scale})`;
    state.cardsLayer.style.transform = t;
    state.zoomLayer.setAttribute('transform',
        `translate(${state.panX}, ${state.panY}) scale(${state.scale})`);
}

/* ───────────── pan / zoom (module-level wrap listeners) ───────────── */

state.wrap.addEventListener('wheel', (ev) => {
    ev.preventDefault();
    const rect = state.wrap.getBoundingClientRect();
    const cx = ev.clientX - rect.left;
    const cy = ev.clientY - rect.top;
    const delta = ev.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.max(0.2, Math.min(4, state.scale * delta));
    if (newScale === state.scale) return;
    // Anchor zoom so the world point under the cursor stays under the cursor.
    state.panX = cx - (cx - state.panX) * (newScale / state.scale);
    state.panY = cy - (cy - state.panY) * (newScale / state.scale);
    state.scale = newScale;
    state.targetPanX = state.panX;
    state.targetPanY = state.panY;
    state.targetScale = state.scale;
    applyTransform();
}, { passive: false });

state.wrap.addEventListener('mousedown', (ev) => {
    if (ev.target.closest('.tcard') || ev.target.closest('.tether-edge') ||
        ev.target.closest('.tether-panel') ||
        ev.target.closest('.tether-toolbar') || ev.target.closest('.tether-controls')) return;
    // Cancel any running animation so drag starts from the current position.
    state.panning = false;
    state.targetPanX = state.panX;
    state.targetPanY = state.panY;
    state.targetScale = state.scale;
    state.dragging = true;
    state.dragStart = { x: ev.clientX - state.panX, y: ev.clientY - state.panY };
});

window.addEventListener('mousemove', (ev) => {
    if (!state.dragging) return;
    state.panX = ev.clientX - state.dragStart.x;
    state.panY = ev.clientY - state.dragStart.y;
    state.targetPanX = state.panX;
    state.targetPanY = state.panY;
    applyTransform();
});

window.addEventListener('mouseup', () => { state.dragging = false; });

// Click empty canvas → clear selection
state.wrap.addEventListener('click', (ev) => {
    if (ev.target.closest('.tcard') || ev.target.closest('.tether-edge') ||
        ev.target.closest('.tether-panel') ||
        ev.target.closest('.tether-toolbar') || ev.target.closest('.tether-controls')) return;
    clearSelection();
});
