// Shared D3 chart helpers used by chart_form.html and the public+admin
// dashboard_detail templates. Depends on the global `d3` loaded via the
// CDN <script> tag in each consuming template.

export function readCssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function buildTheme() {
    const palette = [
        readCssVar('--c-red'),
        readCssVar('--c-cyan'),
        readCssVar('--c-lime'),
        readCssVar('--c-orange'),
        readCssVar('--c-pink'),
    ].filter(Boolean);
    return {
        colors: palette,
        text: readCssVar('--text'),
        textSec: readCssVar('--text-sec'),
        textMuted: readCssVar('--text-muted'),
        border: readCssVar('--border'),
        surface: readCssVar('--surface'),
        accent: readCssVar('--c-red'),
        mode: document.documentElement.getAttribute('data-theme') || 'light',
    };
}

export function renderChart(container, d3Code, data, theme) {
    container.innerHTML = '';
    try {
        const fn = new Function('data', 'container', 'd3', 'theme', d3Code);
        fn(data, container, window.d3, theme);
    } catch (e) {
        container.innerHTML = '<div class="chart-card__error"><i class="fa-solid fa-triangle-exclamation"></i> Render error: ' + e.message + '</div>';
    }
}

export function timesince(iso) {
    if (!iso) return 'Not cached';
    const then = new Date(iso).getTime();
    if (isNaN(then)) return 'Not cached';
    const diff = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + ' min ago';
    if (diff < 86400) return Math.floor(diff / 3600) + ' hr ago';
    return Math.floor(diff / 86400) + ' d ago';
}

export function setRefreshInfo(chartId, iso) {
    const el = document.querySelector('[data-refresh-info="' + chartId + '"]');
    if (el) el.innerHTML = '<i class="fa-regular fa-clock"></i> ' + timesince(iso);
}

export function observeThemeChanges(callback) {
    const observer = new MutationObserver(function (mutations) {
        for (const m of mutations) {
            if (m.attributeName === 'data-theme') {
                callback();
                break;
            }
        }
    });
    observer.observe(document.documentElement, { attributes: true });
    return observer;
}
