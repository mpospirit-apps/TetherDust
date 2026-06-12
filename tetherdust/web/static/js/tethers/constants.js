// Pure constants and tiny SVG/string helpers shared across the tether modules.

export const REL_COLOR = {
    'reads': 'var(--c-cyan)',
    'writes': 'var(--c-pink)',
    'references': 'var(--c-lime)',
    'maps-to': 'var(--c-orange)',
};

export const KIND_LABEL = {
    'code-file': 'File',
    'code-symbol': 'Symbol',
    'db-table': 'Table',
    'db-column': 'Column',
};

export const KIND_ICON = {
    'code-file': 'fa-file-lines',
    'db-table': 'fa-table',
};

export const ALL_RELS = ['reads', 'writes', 'references', 'maps-to'];

export const ROW_HEIGHT = 26;
export const HEADER_HEIGHT = 36;
export const CARD_PADDING_Y = 8;
export const MAX_INLINE_ROWS = 8;
export const PREVIEW_ROWS = 5;
export const MIN_CARD_W = 220;
export const MAX_CARD_W = 360;

// Spread (charge repulsion) — controls how far apart cards push. Higher = more
// air between cards. Persisted across visits via localStorage.
export const DEFAULT_SPREAD = 1500;
export const SPREAD_KEY = 'tether:spread';

export function getSpread() {
    const stored = Number(localStorage.getItem(SPREAD_KEY));
    return Number.isFinite(stored) && stored > 0 ? stored : DEFAULT_SPREAD;
}

// Gap — how far each lane's center sits from the seam, as a fraction of canvas
// width. Larger = wider wall between the code and db columns. Persisted too.
export const DEFAULT_GAP = 0.30;
export const GAP_KEY = 'tether:gap';

export function getGap() {
    const stored = Number(localStorage.getItem(GAP_KEY));
    return Number.isFinite(stored) && stored > 0 ? stored : DEFAULT_GAP;
}

export function svgEl(tag, attrs) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    if (attrs) for (const k of Object.keys(attrs)) el.setAttribute(k, attrs[k]);
    return el;
}

export function cssEscape(s) {
    return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/(["\\])/g, '\\$1');
}

export function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}
