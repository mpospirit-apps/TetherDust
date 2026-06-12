// Docsource generation page: custom select dropdowns, destination-folder
// combo, status polling, markdown result rendering. The prompt is built server-side.
//
// URLs come from data-* attrs on <form id="doc-generate-form">.
// dest_folders is read from <script type="application/json" id="dest-folders">.
// Depends on global `marked` and `hljs` from CDN tags in the parent template.

const form = document.getElementById('doc-generate-form');
if (form) {
    initCustomSelects();
    initMain();
}

// ─── Custom Select Component ───────────────────────────────────────────
function initCustomSelects() {
    function initCustomSelect(sel) {
        if (sel.dataset.customized) return;
        sel.dataset.customized = '1';
        sel.style.display = 'none';

        const wrap = document.createElement('div');
        wrap.className = 'custom-select';
        sel.parentNode.insertBefore(wrap, sel);
        wrap.appendChild(sel);

        const trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = 'custom-select__trigger';
        const selText = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : '';
        trigger.innerHTML = '<span>' + selText + '</span><i class="fa-solid fa-chevron-down"></i>';
        wrap.insertBefore(trigger, sel);

        const dropdown = document.createElement('div');
        dropdown.className = 'custom-select__dropdown';
        wrap.appendChild(dropdown);

        function buildOptions() {
            dropdown.innerHTML = '';
            for (let i = 0; i < sel.options.length; i++) {
                const opt = document.createElement('div');
                opt.className = 'custom-select__option';
                if (i === sel.selectedIndex) opt.classList.add('is-selected');
                opt.dataset.value = sel.options[i].value;
                opt.dataset.index = i;
                opt.textContent = sel.options[i].text;
                if (sel.options[i].disabled) {
                    opt.style.opacity = '.4';
                    opt.style.pointerEvents = 'none';
                }
                dropdown.appendChild(opt);
            }
        }
        buildOptions();

        trigger.addEventListener('click', function (e) {
            e.stopPropagation();
            const wasOpen = wrap.classList.contains('is-open');
            closeAllSelects();
            if (!wasOpen) wrap.classList.add('is-open');
        });

        dropdown.addEventListener('click', function (e) {
            const opt = e.target.closest('.custom-select__option');
            if (!opt || sel.options[opt.dataset.index].disabled) return;
            sel.selectedIndex = parseInt(opt.dataset.index);
            sel.dispatchEvent(new Event('change', { bubbles: true }));
            trigger.querySelector('span').textContent = opt.textContent;
            dropdown.querySelectorAll('.is-selected').forEach(o => o.classList.remove('is-selected'));
            opt.classList.add('is-selected');
            wrap.classList.remove('is-open');
        });

        trigger.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { wrap.classList.remove('is-open'); return; }
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                if (!wrap.classList.contains('is-open')) { wrap.classList.add('is-open'); return; }
                const focused = dropdown.querySelector('.is-focused') || dropdown.querySelector('.is-selected');
                const items = dropdown.querySelectorAll('.custom-select__option:not([style*="pointer-events"])');
                const arr = Array.prototype.slice.call(items);
                const idx = focused ? arr.indexOf(focused) : -1;
                const next = e.key === 'ArrowDown' ? Math.min(idx + 1, arr.length - 1) : Math.max(idx - 1, 0);
                dropdown.querySelectorAll('.is-focused').forEach(o => o.classList.remove('is-focused'));
                arr[next].classList.add('is-focused');
                arr[next].scrollIntoView({ block: 'nearest' });
            }
            if (e.key === 'Enter' && wrap.classList.contains('is-open')) {
                e.preventDefault();
                const f = dropdown.querySelector('.is-focused');
                if (f) f.click();
            }
        });

        sel._customSelect = {
            rebuild: function () {
                buildOptions();
                const txt = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : '';
                trigger.querySelector('span').textContent = txt;
            },
            wrap,
        };
    }

    function closeAllSelects() {
        document.querySelectorAll('.custom-select.is-open').forEach(w => w.classList.remove('is-open'));
    }
    document.addEventListener('click', closeAllSelects);

    document.querySelectorAll('#doc-ai-step select.form-control').forEach(initCustomSelect);
}

// ─── Main: form + polling + markdown rendering ─────────────────────────
function initMain() {
    const generateUrl = form.dataset.generateUrl;
    const statusUrlTemplate = form.dataset.statusUrlTemplate;

    let folders = [];
    const foldersTag = document.getElementById('dest-folders');
    if (foldersTag) {
        try { folders = JSON.parse(foldersTag.textContent); } catch (_) {}
    }

    const formStep = document.getElementById('doc-ai-step');
    const loadingStep = document.getElementById('doc-loading-step');
    const resultStep = document.getElementById('doc-result-step');

    function showStep(id) {
        formStep.style.display = id === 'doc-ai-step' ? '' : 'none';
        loadingStep.style.display = id === 'doc-loading-step' ? '' : 'none';
        resultStep.style.display = id === 'doc-result-step' ? '' : 'none';

        const title = document.getElementById('page-title');
        if (id === 'doc-loading-step') title.textContent = 'Generating Documentation…';
        else if (id === 'doc-result-step') title.textContent = 'Generation Complete';
        else title.textContent = 'Create Documentation with AI';
    }

    // ── Destination folder combo input ──
    (function () {
        const combo = document.getElementById('dest-combo');
        const input = document.getElementById('dest-input');
        const dropdown = document.getElementById('dest-dropdown');
        const preview = document.getElementById('dest-path-preview');

        function escapeHtml(s) {
            const d = document.createElement('div');
            d.textContent = s;
            return d.innerHTML;
        }

        function buildDropdown() {
            const q = input.value.trim().toLowerCase();
            dropdown.innerHTML = '';
            const matches = folders.filter(f => f.toLowerCase().indexOf(q) !== -1);
            if (matches.length === 0 && !q) {
                const empty = document.createElement('div');
                empty.className = 'combo-input__empty';
                empty.textContent = 'No existing folders';
                dropdown.appendChild(empty);
            } else {
                matches.forEach(function (f) {
                    const item = document.createElement('div');
                    item.className = 'combo-input__item';
                    if (input.value.trim() === f) item.classList.add('is-selected');
                    item.textContent = f;
                    item.dataset.value = f;
                    dropdown.appendChild(item);
                });
            }
            const exactMatch = q && folders.some(f => f.toLowerCase() === q);
            if (q && !exactMatch) {
                const create = document.createElement('div');
                create.className = 'combo-input__item combo-input__item--create';
                create.innerHTML = '+ Create &ldquo;' + escapeHtml(input.value.trim()) + '&rdquo;';
                create.dataset.value = input.value.trim();
                dropdown.appendChild(create);
            }
        }

        function openDropdown() { buildDropdown(); combo.classList.add('is-open'); }
        function closeDropdown() { combo.classList.remove('is-open'); clearFocus(); }

        function clearFocus() {
            dropdown.querySelectorAll('.is-focused').forEach(el => el.classList.remove('is-focused'));
        }

        function updatePreview() {
            const dest = input.value.trim();
            const docName = form.querySelector('[name="doc_name"]').value.trim();
            if (dest || docName) {
                preview.textContent = 'File: documentations/' + (dest || '…') + '/' + (docName || '…') + '.md';
            } else {
                preview.textContent = '';
            }
        }

        input.addEventListener('focus', openDropdown);
        input.addEventListener('input', function () { buildDropdown(); updatePreview(); });
        form.querySelector('[name="doc_name"]').addEventListener('input', updatePreview);

        document.addEventListener('click', function (e) {
            if (!combo.contains(e.target)) closeDropdown();
        });

        dropdown.addEventListener('click', function (e) {
            const item = e.target.closest('.combo-input__item');
            if (!item) return;
            input.value = item.dataset.value;
            closeDropdown();
            updatePreview();
        });

        input.addEventListener('keydown', function (e) {
            if (!combo.classList.contains('is-open')) return;
            const items = dropdown.querySelectorAll('.combo-input__item');
            if (!items.length) return;
            const arr = Array.prototype.slice.call(items);
            const focused = dropdown.querySelector('.is-focused');
            const idx = focused ? arr.indexOf(focused) : -1;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                clearFocus();
                const next = Math.min(idx + 1, arr.length - 1);
                arr[next].classList.add('is-focused');
                arr[next].scrollIntoView({ block: 'nearest' });
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                clearFocus();
                const prev = Math.max(idx - 1, 0);
                arr[prev].classList.add('is-focused');
                arr[prev].scrollIntoView({ block: 'nearest' });
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (focused) {
                    input.value = focused.dataset.value;
                    closeDropdown();
                    updatePreview();
                }
            } else if (e.key === 'Escape') {
                closeDropdown();
            }
        });
    })();

    // ── Loading elapsed timer ──
    const loadingTimer = { interval: null, startTime: 0 };

    function startLoadingTimer() {
        const elapsedEl = document.getElementById('doc-loading-elapsed');
        loadingTimer.startTime = Date.now();
        elapsedEl.textContent = '';
        loadingTimer.interval = setInterval(function () {
            const secs = Math.floor((Date.now() - loadingTimer.startTime) / 1000);
            const m = Math.floor(secs / 60);
            const s = secs % 60;
            elapsedEl.textContent = (m > 0 ? m + 'm ' : '') + s + 's elapsed';
        }, 1000);
    }

    function stopLoadingTimer() {
        if (loadingTimer.interval) clearInterval(loadingTimer.interval);
    }

    // ── Configure marked.js for rendering ──
    window.marked.setOptions({
        highlight: function (code, lang) {
            if (lang && window.hljs.getLanguage(lang)) return window.hljs.highlight(code, { language: lang }).value;
            return window.hljs.highlightAuto(code).value;
        }
    });

    function escapeHtmlContent(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // ── Polling state ──
    let pollTimer = null;

    function showResult(data, docName) {
        stopLoadingTimer();
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        showStep('doc-result-step');
        const el = document.getElementById('doc-result-content');
        const elapsed = Math.floor((Date.now() - loadingTimer.startTime) / 1000);
        const timeStr = elapsed >= 60 ? Math.floor(elapsed / 60) + 'm ' + (elapsed % 60) + 's' : elapsed + 's';

        if (data.status === 'failed') {
            el.innerHTML = '<div style="text-align:center">' +
                '<i class="fa-solid fa-circle-xmark" style="font-size:2rem;color:var(--danger);margin-bottom:var(--md);display:block"></i>' +
                '<h3>Generation Failed</h3>' +
                '<p class="text-sec" style="font-size:var(--text-sm)">' + escapeHtmlContent(data.error || 'Unknown error') + '</p>' +
                '</div>';
            return;
        }

        const isPartial = data.status === 'partial';
        const iconClass = isPartial ? 'fa-triangle-exclamation' : 'fa-circle-check';
        const iconColor = isPartial ? 'var(--warning)' : 'var(--success)';
        const statusLabel = isPartial ? 'Documentation Generated (with warnings)' : 'Documentation Generated';

        let warningHtml = '';
        if (data.warnings && data.warnings.length) {
            warningHtml = '<div style="background:rgba(242,149,68,.1);border:1px solid var(--warning);border-radius:8px;padding:var(--sm) var(--md);margin-top:var(--md);font-size:var(--text-sm)">' +
                '<strong style="color:var(--warning)"><i class="fa-solid fa-triangle-exclamation"></i> Warnings</strong><ul style="margin:var(--xs) 0 0;padding-left:1.2em">';
            data.warnings.forEach(w => { warningHtml += '<li>' + escapeHtmlContent(w) + '</li>'; });
            warningHtml += '</ul></div>';
        }

        el.innerHTML =
            '<div class="doc-result-grid">' +
                '<div class="doc-result-summary">' +
                    '<i class="fa-solid ' + iconClass + '" style="font-size:2rem;color:' + iconColor + ';display:block;margin-bottom:var(--md)"></i>' +
                    '<h3>' + statusLabel + '</h3>' +
                    '<p class="text-sec" style="font-size:var(--text-sm)">Created ' + (data.file_count || 1) + ' file(s) in <code>' + escapeHtmlContent(data.folder || '') + '</code></p>' +
                    '<p class="text-sec" style="font-size:var(--text-xs);color:var(--text-muted);margin-top:var(--xs)">Completed in ' + timeStr + '</p>' +
                    warningHtml +
                '</div>' +
                '<div class="doc-result-preview">' +
                    '<div class="doc-result-preview__title"><i class="fa-solid fa-file-lines"></i> ' + escapeHtmlContent(docName) + '.md</div>' +
                    '<div class="doc-result-preview__content markdown-body">' +
                        window.DOMPurify.sanitize(window.marked.parse(data.content || '')) +
                '</div></div>' +
            '</div>';
    }

    function startPolling(logId, docName) {
        const statusUrl = statusUrlTemplate.replace('/0/', '/' + logId + '/');
        let fileSeenOnce = false;

        pollTimer = setInterval(function () {
            fetch(statusUrl)
                .then(r => r.json())
                .then(function (data) {
                    if (data.status === 'running') {
                        const statusLine = document.getElementById('doc-loading-status');
                        let newText = null;
                        if (data.agent_output) newText = data.agent_output;
                        else if (data.file_exists && !fileSeenOnce) {
                            fileSeenOnce = true;
                            newText = 'File created — agent is finishing up…';
                        }
                        if (newText && statusLine && statusLine.textContent !== newText) {
                            statusLine.style.opacity = '0';
                            setTimeout((function (t) {
                                return function () {
                                    statusLine.textContent = t;
                                    statusLine.style.opacity = '1';
                                };
                            })(newText), 200);
                        }
                        return;
                    }
                    showResult(data, docName);
                })
                .catch(function () {});
        }, 3000);
    }

    // ── Generate (send prompt) ──
    document.getElementById('doc-send-prompt').addEventListener('click', function () {
        const docName = form.querySelector('[name="doc_name"]').value.trim();
        const agent = form.querySelector('[name="agent"]').value;
        const dest = form.querySelector('[name="destination"]').value.trim();
        if (!docName) { alert('Please enter a documentation name.'); return; }
        if (!agent) { alert('Please select an AI model.'); return; }
        if (!dest) { alert('Please enter a destination folder.'); return; }

        showStep('doc-loading-step');
        startLoadingTimer();

        const formData = new FormData(form);

        fetch(generateUrl, {
            method: 'POST',
            body: formData
        })
        .then(r => r.json())
        .then(function (data) {
            if (!data.success) {
                stopLoadingTimer();
                showStep('doc-result-step');
                document.getElementById('doc-result-content').innerHTML = '<div style="text-align:center">' +
                    '<i class="fa-solid fa-circle-xmark" style="font-size:2rem;color:var(--danger);margin-bottom:var(--md);display:block"></i>' +
                    '<h3>Generation Failed</h3>' +
                    '<p class="text-sec" style="font-size:var(--text-sm)">' + escapeHtmlContent(data.error) + '</p>' +
                    '</div>';
                return;
            }
            startPolling(data.log_id, docName);
        })
        .catch(function (err) {
            stopLoadingTimer();
            showStep('doc-result-step');
            document.getElementById('doc-result-content').innerHTML = '<div style="text-align:center">' +
                '<i class="fa-solid fa-circle-xmark" style="font-size:2rem;color:var(--danger);margin-bottom:var(--md);display:block"></i>' +
                '<h3>Request Failed</h3>' +
                '<p class="text-sec" style="font-size:var(--text-sm)">' + escapeHtmlContent(err.message) + '</p>' +
                '</div>';
        });
    });
}
