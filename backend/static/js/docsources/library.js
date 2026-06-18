// Documentation library generation page: custom select, name preview,
// status polling, file-tree result rendering. The prompt is built server-side.
//
// URLs come from data-* attrs on <form id="doc-generate-form">.
// existing_folders is read from <script type="application/json" id="existing-folders">.

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
    }

    function closeAllSelects() {
        document.querySelectorAll('.custom-select.is-open').forEach(w => w.classList.remove('is-open'));
    }
    document.addEventListener('click', closeAllSelects);

    document.querySelectorAll('#doc-ai-step select.form-control').forEach(initCustomSelect);
}

// ─── Main: form + polling + result rendering ───────────────────────────
function initMain() {
    const generateUrl = form.dataset.generateUrl;
    const statusUrlTemplate = form.dataset.statusUrlTemplate;

    let existingFolders = [];
    const foldersTag = document.getElementById('existing-folders');
    if (foldersTag) {
        try { existingFolders = JSON.parse(foldersTag.textContent); } catch (_) {}
    }

    const formStep = document.getElementById('doc-ai-step');
    const loadingStep = document.getElementById('doc-loading-step');
    const resultStep = document.getElementById('doc-result-step');

    function showStep(id) {
        formStep.style.display = id === 'doc-ai-step' ? '' : 'none';
        loadingStep.style.display = id === 'doc-loading-step' ? '' : 'none';
        resultStep.style.display = id === 'doc-result-step' ? '' : 'none';

        const title = document.getElementById('page-title');
        if (id === 'doc-loading-step') title.textContent = 'Building Documentation Library…';
        else if (id === 'doc-result-step') title.textContent = 'Library Created';
        else title.textContent = 'Create Documentation Library';
    }

    function escapeHtml(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function fmtSize(bytes) {
        if (bytes == null) return '';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    // ── Library name preview + existing-folder warning ──
    const nameInput = document.getElementById('lib-name-input');
    const namePreview = document.getElementById('lib-path-preview');
    const nameWarning = document.getElementById('lib-name-warning');

    function sanitizeName(v) {
        return v.replace(/\\/g, '/').split('/').filter(p => p && p !== '..').join('/');
    }

    function updateNamePreview() {
        const root = sanitizeName(nameInput.value.trim());
        namePreview.textContent = root ? 'Folder: documentations/' + root + '/' : '';
        const exists = root && existingFolders.some(f => f.toLowerCase() === root.toLowerCase());
        nameWarning.style.display = exists ? '' : 'none';
    }
    nameInput.addEventListener('input', updateNamePreview);

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

    // ── Polling state ──
    let pollTimer = null;

    function showResult(data) {
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
                '<p class="text-sec" style="font-size:var(--text-sm)">' + escapeHtml(data.error || 'Unknown error') + '</p>' +
                '</div>';
            return;
        }

        const isPartial = data.status === 'partial';
        const iconClass = isPartial ? 'fa-triangle-exclamation' : 'fa-circle-check';
        const iconColor = isPartial ? 'var(--warning)' : 'var(--success)';
        const statusLabel = isPartial ? 'Library Created (with warnings)' : 'Library Created';

        let warningHtml = '';
        if (data.warnings && data.warnings.length) {
            warningHtml = '<div style="background:rgba(242,149,68,.1);border:1px solid var(--warning);border-radius:8px;padding:var(--sm) var(--md);margin-top:var(--md);font-size:var(--text-sm)">' +
                '<strong style="color:var(--warning)"><i class="fa-solid fa-triangle-exclamation"></i> Warnings</strong><ul style="margin:var(--xs) 0 0;padding-left:1.2em">';
            data.warnings.forEach(w => { warningHtml += '<li>' + escapeHtml(w) + '</li>'; });
            warningHtml += '</ul></div>';
        }

        const files = data.files || [];
        let filesHtml = '<p class="text-sec" style="font-size:var(--text-sm)">No files were created.</p>';
        if (files.length) {
            filesHtml = '<ul style="list-style:none;margin:0;padding:0">';
            files.forEach(function (f) {
                filesHtml += '<li style="display:flex;justify-content:space-between;gap:var(--md);padding:var(--xs) 0;border-bottom:1px solid rgba(26,26,26,.06);font-size:var(--text-sm)">' +
                    '<span><i class="fa-solid fa-file-lines text-sec"></i> ' + escapeHtml(f.path) + '</span>' +
                    '<span class="text-sec" style="font-size:var(--text-xs)">' + fmtSize(f.size) + '</span>' +
                    '</li>';
            });
            filesHtml += '</ul>';
        }

        el.innerHTML =
            '<div style="text-align:center;margin-bottom:var(--lg)">' +
                '<i class="fa-solid ' + iconClass + '" style="font-size:2rem;color:' + iconColor + ';display:block;margin-bottom:var(--md)"></i>' +
                '<h3>' + statusLabel + '</h3>' +
                '<p class="text-sec" style="font-size:var(--text-sm)">Created ' + (data.file_count || files.length) + ' file(s) in <code>' + escapeHtml(data.folder || '') + '/</code>' +
                    (data.total_size != null ? ' &middot; ' + fmtSize(data.total_size) : '') + '</p>' +
                '<p class="text-sec" style="font-size:var(--text-xs);color:var(--text-muted);margin-top:var(--xs)">Completed in ' + timeStr + '</p>' +
                warningHtml +
            '</div>' +
            '<div class="doc-result-preview__title"><i class="fa-solid fa-folder-tree"></i> Files</div>' +
            '<div style="margin-top:var(--sm)">' + filesHtml + '</div>';
    }

    function startPolling(logId) {
        const statusUrl = statusUrlTemplate.replace('/0/', '/' + logId + '/');

        pollTimer = setInterval(function () {
            fetch(statusUrl)
                .then(r => r.json())
                .then(function (data) {
                    if (data.status === 'running') {
                        const statusLine = document.getElementById('doc-loading-status');
                        let newText = null;
                        if (data.file_count) newText = data.file_count + ' file(s) created so far…';
                        if (data.agent_output) newText = data.agent_output;
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
                    showResult(data);
                })
                .catch(function () {});
        }, 3000);
    }

    // ── Generate ──
    document.getElementById('doc-send-prompt').addEventListener('click', function () {
        const name = nameInput.value.trim();
        const agent = form.querySelector('[name="agent"]').value;
        if (!name) { alert('Please enter a library name.'); return; }
        if (!agent) { alert('Please select an agent.'); return; }

        showStep('doc-loading-step');
        startLoadingTimer();

        const formData = new FormData(form);

        fetch(generateUrl, { method: 'POST', body: formData })
            .then(r => r.json())
            .then(function (data) {
                if (!data.success) {
                    stopLoadingTimer();
                    showStep('doc-result-step');
                    document.getElementById('doc-result-content').innerHTML = '<div style="text-align:center">' +
                        '<i class="fa-solid fa-circle-xmark" style="font-size:2rem;color:var(--danger);margin-bottom:var(--md);display:block"></i>' +
                        '<h3>Generation Failed</h3>' +
                        '<p class="text-sec" style="font-size:var(--text-sm)">' + escapeHtml(data.error) + '</p>' +
                        '</div>';
                    return;
                }
                startPolling(data.log_id);
            })
            .catch(function (err) {
                stopLoadingTimer();
                showStep('doc-result-step');
                document.getElementById('doc-result-content').innerHTML = '<div style="text-align:center">' +
                    '<i class="fa-solid fa-circle-xmark" style="font-size:2rem;color:var(--danger);margin-bottom:var(--md);display:block"></i>' +
                    '<h3>Request Failed</h3>' +
                    '<p class="text-sec" style="font-size:var(--text-sm)">' + escapeHtml(err.message) + '</p>' +
                    '</div>';
            });
    });

    updateNamePreview();
}
