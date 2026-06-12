// Chart-edit form: live D3 preview + AI chat WebSocket. Reads URLs and
// edit-mode state from data-* attributes on the <form id="chart-form">.
// Cached data (when editing an existing chart) comes from a sibling
// <script type="application/json" id="chart-cached-data"> element so the
// JSON payload can contain quotes safely.

import { buildTheme, observeThemeChanges } from './render.js';

const form = document.getElementById('chart-form');
if (form && form.dataset.previewUrl) {
    init();
}

function init() {
    const previewUrl = form.dataset.previewUrl;
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    const instancePk = form.dataset.instancePk || '';
    const stateUrl = form.dataset.stateUrl || '';
    const agentName = form.dataset.activeAgent || '';

    const dbEl = document.getElementById('id_database');
    const sqlEl = document.getElementById('id_sql_query');
    const d3El = document.getElementById('id_custom_d3_code');
    const titleEl = document.getElementById('id_title');
    const descEl = document.getElementById('id_description');
    const previewEl = document.getElementById('chart-preview-container');
    const previewStatus = document.getElementById('preview-status');
    const previewError = document.getElementById('chart-preview-error');
    const runBtn = document.getElementById('preview-run-btn');

    let lastData = null;
    let renderDebounce = null;

    function showError(msg) {
        if (!msg) {
            previewError.classList.remove('is-visible');
            previewError.textContent = '';
            return;
        }
        previewError.textContent = msg;
        previewError.classList.add('is-visible');
    }

    function setStatus(txt) {
        previewStatus.textContent = txt;
    }

    function renderPreview() {
        if (lastData == null) {
            previewEl.innerHTML = '<div class="chart-preview-empty">Click <strong>Run Query</strong> first to load data.</div>';
            return;
        }
        const code = (d3El && d3El.value || '').trim();
        if (!code) {
            previewEl.innerHTML = '<div class="chart-preview-empty">Write d3 code to render the chart.</div>';
            return;
        }
        previewEl.innerHTML = '';
        const theme = buildTheme();
        try {
            const fn = new Function('data', 'container', 'd3', 'theme', code);
            fn(lastData.data, previewEl, window.d3, theme);
            showError(null);
        } catch (e) {
            showError('Render error: ' + (e && e.message ? e.message : String(e)));
        }
    }

    function runQuery() {
        const databaseId = dbEl ? dbEl.value : '';
        const sql = sqlEl ? sqlEl.value.trim() : '';
        if (!databaseId) { showError('Pick a database first.'); return; }
        if (!sql) { showError('Enter a SQL query first.'); return; }
        showError(null);
        setStatus('Running...');
        runBtn.disabled = true;
        fetch(previewUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({ database_id: databaseId, sql_query: sql }),
        })
        .then(r => r.json().then(body => ({ status: r.status, body })))
        .then(function (res) {
            runBtn.disabled = false;
            if (res.status !== 200 || res.body.error) {
                lastData = null;
                setStatus('Error');
                showError(res.body.error || ('HTTP ' + res.status));
                previewEl.innerHTML = '<div class="chart-preview-empty">Fix the error and Run Query again.</div>';
                return;
            }
            lastData = { columns: res.body.columns || [], data: res.body.data || [] };
            setStatus((lastData.data.length) + ' rows · just now');
            renderPreview();
        })
        .catch(function (err) {
            runBtn.disabled = false;
            lastData = null;
            setStatus('Error');
            showError('Request failed: ' + (err && err.message ? err.message : String(err)));
        });
    }

    runBtn.addEventListener('click', runQuery);

    if (d3El) {
        d3El.addEventListener('input', function () {
            if (renderDebounce) clearTimeout(renderDebounce);
            renderDebounce = setTimeout(renderPreview, 600);
        });
    }

    observeThemeChanges(renderPreview);

    // Edit mode: prefer the chart's cached data so the preview renders
    // instantly without hitting the database.
    const cachedTag = document.getElementById('chart-cached-data');
    if (cachedTag && cachedTag.textContent.trim()) {
        let initialCached = null;
        try { initialCached = JSON.parse(cachedTag.textContent); } catch (_) {}
        if (initialCached && initialCached.data) {
            lastData = { columns: initialCached.columns || [], data: initialCached.data };
            const refreshedAt = initialCached.refreshed_at;
            setStatus(lastData.data.length + ' rows · cached'
                      + (refreshedAt ? ' · ' + new Date(refreshedAt).toLocaleString() : ''));
            renderPreview();
        }
    }

    // ── AI chat panel (only in edit mode) ──────────────────────────────
    if (instancePk && stateUrl) {
        initAgentChat({
            chartId: instancePk,
            stateUrl,
            agentName,
            onStateUpdate: ({ titleChanged, descChanged, sqlChanged, d3Changed }) => {
                if (sqlChanged) runQuery();
                else if (d3Changed) renderPreview();
            },
        });
    }

    function initAgentChat({ chartId, stateUrl, agentName, onStateUpdate }) {
        const aichatForm = document.getElementById('aichat-form');
        const aichatInput = document.getElementById('aichat-input');
        const aichatSend = document.getElementById('aichat-send');
        const transcript = document.getElementById('aichat-transcript');
        const connStatus = document.getElementById('aichat-conn-status');
        if (!aichatForm) return;

        let ws = null;
        let streaming = false;
        let currentAssistantEl = null;
        let currentWorkingEl = null;

        function setConn(txt, cls) {
            connStatus.textContent = txt;
            connStatus.style.color = cls || '';
        }

        function buildDotsEl() {
            const dots = document.createElement('span');
            dots.className = 'typing-dots';
            for (let i = 0; i < 5; i++) {
                dots.appendChild(document.createElement('span')).className = 'typing-dot';
            }
            return dots;
        }

        function clearEmptyState() {
            const empty = transcript.querySelector('.chart-aichat-empty');
            if (empty) empty.remove();
        }

        function addMessage(role, text) {
            clearEmptyState();
            const wrap = document.createElement('div');
            wrap.className = 'chart-aichat-msg chart-aichat-msg--' + role;
            const label = document.createElement('div');
            label.className = 'chart-aichat-msg__label';
            label.textContent = role === 'user' ? 'You' : (role === 'assistant' ? 'Agent' : 'Error');
            const body = document.createElement('div');
            body.textContent = text || '';
            wrap.appendChild(label);
            wrap.appendChild(body);
            transcript.appendChild(wrap);
            transcript.scrollTop = transcript.scrollHeight;
            return body;
        }

        function addAssistantBubbleWithDots() {
            clearEmptyState();
            const wrap = document.createElement('div');
            wrap.className = 'chart-aichat-msg chart-aichat-msg--assistant';
            const label = document.createElement('div');
            label.className = 'chart-aichat-msg__label';
            label.textContent = 'Agent';
            const body = document.createElement('div');
            const dots = buildDotsEl();
            body.appendChild(dots);
            wrap.appendChild(label);
            wrap.appendChild(body);
            transcript.appendChild(wrap);
            transcript.scrollTop = transcript.scrollHeight;
            currentWorkingEl = dots;
            return body;
        }

        function connectWs() {
            if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
            const proto = (location.protocol === 'https:') ? 'wss:' : 'ws:';
            ws = new WebSocket(proto + '//' + location.host + '/ws/chart-edit/' + chartId + '/');
            setConn('connecting...', '');
            ws.onopen = () => setConn('Connected to ' + agentName, 'var(--c-lime)');
            ws.onclose = function () {
                setConn('disconnected', 'var(--text-muted)');
                if (streaming) {
                    addMessage('error', 'Connection lost during agent response.');
                    streaming = false;
                    aichatSend.disabled = false;
                    currentAssistantEl = null;
                }
            };
            ws.onerror = () => setConn('error', 'var(--danger)');
            ws.onmessage = function (evt) {
                let data;
                try { data = JSON.parse(evt.data); } catch (e) { return; }
                if (data.type === 'ready') {
                    // nothing to show — the bubble's dots cover the working state
                } else if (data.type === 'stream_start') {
                    currentAssistantEl = addAssistantBubbleWithDots();
                } else if (data.type === 'stream_chunk') {
                    if (currentAssistantEl) {
                        if (currentWorkingEl && currentWorkingEl.parentNode === currentAssistantEl) {
                            currentAssistantEl.removeChild(currentWorkingEl);
                            currentWorkingEl = null;
                        }
                        currentAssistantEl.textContent += (data.content || '');
                        transcript.scrollTop = transcript.scrollHeight;
                    }
                } else if (data.type === 'stream_end') {
                    streaming = false;
                    aichatSend.disabled = false;
                    if (currentWorkingEl && currentAssistantEl &&
                        currentWorkingEl.parentNode === currentAssistantEl) {
                        currentAssistantEl.removeChild(currentWorkingEl);
                        currentAssistantEl.textContent = '(done)';
                    }
                    currentWorkingEl = null;
                    reloadChartState();
                } else if (data.type === 'error') {
                    streaming = false;
                    aichatSend.disabled = false;
                    currentAssistantEl = null;
                    currentWorkingEl = null;
                    addMessage('error', data.message || 'Unknown error');
                }
            };
        }

        function reloadChartState() {
            fetch(stateUrl)
            .then(r => r.json())
            .then(function (state) {
                const changed = {
                    titleChanged: false, descChanged: false,
                    sqlChanged: false, d3Changed: false,
                };
                if (titleEl && state.title !== titleEl.value) {
                    titleEl.value = state.title;
                    changed.titleChanged = true;
                }
                if (descEl && (state.description || '') !== descEl.value) {
                    descEl.value = state.description || '';
                    changed.descChanged = true;
                }
                if (sqlEl && state.sql_query !== sqlEl.value) {
                    sqlEl.value = state.sql_query;
                    changed.sqlChanged = true;
                }
                if (d3El && (state.custom_d3_code || '') !== d3El.value) {
                    d3El.value = state.custom_d3_code || '';
                    changed.d3Changed = true;
                }
                onStateUpdate(changed);
            })
            .catch(function () {
                addMessage('error', 'Failed to reload chart state — please refresh.');
            });
        }

        aichatForm.addEventListener('submit', function (e) {
            e.preventDefault();
            if (streaming) return;
            const msg = (aichatInput.value || '').trim();
            if (!msg) return;
            connectWs();
            const trySend = function (retry) {
                if (ws.readyState === WebSocket.OPEN) {
                    addMessage('user', msg);
                    aichatInput.value = '';
                    streaming = true;
                    aichatSend.disabled = true;
                    currentAssistantEl = null;
                    ws.send(JSON.stringify({ message: msg }));
                } else if (retry > 0) {
                    setTimeout(() => trySend(retry - 1), 150);
                } else {
                    addMessage('error', 'Could not connect to agent editor.');
                }
            };
            trySend(20);
        });

        // Establish the WS connection on page load so the first send is instant.
        connectWs();
    }
}
