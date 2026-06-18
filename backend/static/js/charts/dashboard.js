// Dashboard view (public + admin). Renders all charts under
// [data-chart-id] using D3 code stored in adjacent <template> tags.
// URL template comes from data-chart-data-url-template on a root element
// (different per page: chat:chart_data_api vs control:chart_data).

import {
    buildTheme,
    renderChart,
    setRefreshInfo,
    observeThemeChanges,
} from './render.js';

const root = document.querySelector('[data-chart-data-url-template]');
if (root) {
    init(root.dataset.chartDataUrlTemplate);
}

function init(dataUrlTemplate) {
    // ── Optional sidebar (only present in the public dashboard view) ───
    const sidebar = document.getElementById('docs-sidebar');
    const toggle = document.getElementById('docs-toggle');
    if (toggle && sidebar) {
        toggle.addEventListener('click', () => sidebar.classList.toggle('collapsed'));
    }
    const search = document.getElementById('dashboards-search');
    if (search) {
        search.addEventListener('input', function () {
            const q = this.value.trim().toLowerCase();
            document.querySelectorAll('.docs-tree .docs-file-btn').forEach(function (btn) {
                const name = btn.querySelector('span').textContent.toLowerCase();
                btn.style.display = (!q || name.includes(q)) ? '' : 'none';
            });
        });
    }

    // ── Chart rendering ────────────────────────────────────────────────
    const chartCache = {};

    function getUrl(chartId, forceRefresh) {
        const url = dataUrlTemplate.replace('/0/', '/' + chartId + '/');
        return forceRefresh ? url + '?refresh=1' : url;
    }

    function loadChart(chartId, opts) {
        opts = opts || {};
        const container = document.getElementById('chart-' + chartId);
        if (!container) return;
        const codeEl = document.querySelector('template[data-for-chart="' + chartId + '"]');
        if (!codeEl) {
            container.innerHTML = '<div class="chart-card__error">No chart code found</div>';
            return;
        }
        const d3Code = codeEl.content.textContent;
        chartCache[chartId] = chartCache[chartId] || { code: d3Code, data: null };
        const theme = buildTheme();

        if (!opts.forceRefresh && chartCache[chartId].data) {
            renderChart(container, d3Code, chartCache[chartId].data, theme);
            return;
        }

        if (!opts.skipLoadingState) {
            container.innerHTML = '<div class="chart-card__loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</div>';
        }

        fetch(getUrl(chartId, !!opts.forceRefresh))
            .then(r => r.json())
            .then(function (response) {
                if (response.error) {
                    container.innerHTML = '<div class="chart-card__error"><i class="fa-solid fa-triangle-exclamation"></i> ' + response.error + '</div>';
                    return;
                }
                chartCache[chartId].data = response.data;
                if (response.refreshed_at) setRefreshInfo(chartId, response.refreshed_at);
                renderChart(container, d3Code, response.data, theme);
            })
            .catch(function () {
                container.innerHTML = '<div class="chart-card__error"><i class="fa-solid fa-triangle-exclamation"></i> Failed to load data</div>';
            });
    }

    function loadAll(opts) {
        document.querySelectorAll('[data-chart-id]').forEach(function (c) {
            loadChart(c.dataset.chartId, opts);
        });
    }

    loadAll();

    // ── Manual refresh buttons ─────────────────────────────────────────
    document.querySelectorAll('[data-refresh-chart]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const chartId = btn.dataset.refreshChart;
            const icon = btn.querySelector('.fa-rotate');
            if (icon) icon.classList.add('spinning');
            if (chartCache[chartId]) chartCache[chartId].data = null;
            fetch(getUrl(chartId, true))
                .then(r => r.json())
                .then(function (response) {
                    if (icon) icon.classList.remove('spinning');
                    const container = document.getElementById('chart-' + chartId);
                    if (response.error) {
                        if (container) container.innerHTML = '<div class="chart-card__error"><i class="fa-solid fa-triangle-exclamation"></i> ' + response.error + '</div>';
                        return;
                    }
                    chartCache[chartId] = chartCache[chartId] || {};
                    chartCache[chartId].data = response.data;
                    if (response.refreshed_at) setRefreshInfo(chartId, response.refreshed_at);
                    const theme = buildTheme();
                    const codeEl = document.querySelector('template[data-for-chart="' + chartId + '"]');
                    if (container && codeEl) renderChart(container, codeEl.content.textContent, response.data, theme);
                })
                .catch(function () {
                    if (icon) icon.classList.remove('spinning');
                    const container = document.getElementById('chart-' + chartId);
                    if (container) container.innerHTML = '<div class="chart-card__error"><i class="fa-solid fa-triangle-exclamation"></i> Failed to load data</div>';
                });
        });
    });

    observeThemeChanges(() => loadAll({ skipLoadingState: true }));
}
