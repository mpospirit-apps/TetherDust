// MCP server detail — Test Connection panel.
// Reads the test endpoint URL and CSRF token from data-* attrs on the
// `mcp-test-btn` button. Auto-runs on page load.

(function () {
    const btn = document.getElementById('mcp-test-btn');
    if (!btn) return;
    const panel = document.getElementById('mcp-test-result');
    const body = document.getElementById('mcp-test-result-body');
    const closeBtn = document.getElementById('mcp-test-close');

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function row(label, value) {
        return '<div style="display:flex;justify-content:space-between;gap:var(--md);padding:4px 0;border-bottom:1px solid rgba(0,0,0,.05)">' +
            '<span class="text-sec">' + esc(label) + '</span>' +
            '<span class="text-mono" style="font-size:12px;text-align:right">' + esc(value) + '</span>' +
            '</div>';
    }

    function render(data) {
        const parts = [];
        const badge = data.ok
            ? '<span class="badge badge-success">OK</span>'
            : '<span class="badge" style="background:var(--danger);color:#fff">FAIL</span>';
        parts.push('<div style="margin-bottom:var(--md)">' + badge + '</div>');

        if (data.error) {
            parts.push('<div style="padding:var(--sm);background:rgba(239,68,68,.08);border-radius:var(--radius);margin-bottom:var(--md)">' +
                '<strong>Error:</strong> ' + esc(data.error) + '</div>');
        }

        parts.push('<h4 style="margin:var(--md) 0 var(--sm)">Request</h4>');
        parts.push('<div>');
        parts.push(row('URL', data.url || '—'));
        parts.push(row('Transport', data.transport || '—'));
        parts.push(row('Bearer token', data.has_auth_token ? 'yes (sent)' : 'no'));
        parts.push(row('Extra headers', (data.header_keys && data.header_keys.length) ? data.header_keys.join(', ') : '—'));
        parts.push('</div>');

        if (data.initialize) {
            parts.push('<h4 style="margin:var(--md) 0 var(--sm)">initialize</h4><div>');
            parts.push(row('HTTP status', data.initialize.status_code));
            parts.push(row('Elapsed', data.initialize.elapsed_ms + ' ms'));
            if (data.initialize.content_type) parts.push(row('Content-Type', data.initialize.content_type));
            if (data.initialize.protocol_version) parts.push(row('Protocol', data.initialize.protocol_version));
            if (data.initialize.server_name) parts.push(row('Server', data.initialize.server_name + (data.initialize.server_version ? ' (' + data.initialize.server_version + ')' : '')));
            if (data.initialize.body_preview) parts.push('<pre style="font-size:11px;white-space:pre-wrap;max-height:160px;overflow:auto;background:var(--bg-warm);color:var(--text);border-left:none;border:1px solid var(--border);box-shadow:none;padding:var(--sm);border-radius:var(--radius);margin-top:var(--sm)">' + esc(data.initialize.body_preview) + '</pre>');
            parts.push('</div>');
        }

        if (data.tools_list) {
            parts.push('<h4 style="margin:var(--md) 0 var(--sm)">tools/list</h4><div>');
            parts.push(row('HTTP status', data.tools_list.status_code));
            parts.push(row('Elapsed', data.tools_list.elapsed_ms + ' ms'));
            if (typeof data.tools_list.count === 'number') parts.push(row('Tool count', data.tools_list.count));
            if (data.tools_list.body_preview) parts.push('<pre style="font-size:11px;white-space:pre-wrap;max-height:160px;overflow:auto;background:var(--bg-warm);color:var(--text);border-left:none;border:1px solid var(--border);box-shadow:none;padding:var(--sm);border-radius:var(--radius);margin-top:var(--sm)">' + esc(data.tools_list.body_preview) + '</pre>');
            parts.push('</div>');

            if (data.tools_list.tools && data.tools_list.tools.length) {
                parts.push('<h4 style="margin:var(--md) 0 var(--sm)">Discovered tools</h4>');
                parts.push('<div class="table-wrap"><table><thead><tr><th>Name</th><th>Description</th></tr></thead><tbody>');
                data.tools_list.tools.forEach(function (t) {
                    parts.push('<tr><td class="text-mono">' + esc(t.name) + '</td><td>' + esc(t.description || '') + '</td></tr>');
                });
                parts.push('</tbody></table></div>');
            }
        }

        body.innerHTML = parts.join('');
    }

    btn.addEventListener('click', function () {
        panel.style.display = '';
        body.innerHTML = '<p class="text-sec">Testing… sending initialize + tools/list</p>';
        btn.disabled = true;
        fetch(btn.dataset.testUrl, {
            method: 'POST',
            headers: { 'X-CSRFToken': btn.dataset.csrf, 'Accept': 'application/json' },
            credentials: 'same-origin',
        })
            .then(r => r.json().then(d => ({ status: r.status, data: d })))
            .then(res => render(res.data))
            .catch(err => { body.innerHTML = '<div style="color:var(--danger)"><strong>Request failed:</strong> ' + esc(err.message || err) + '</div>'; })
            .finally(() => { btn.disabled = false; });
    });

    closeBtn.addEventListener('click', () => { panel.style.display = 'none'; });

    // Auto-run on page load
    btn.click();
})();
