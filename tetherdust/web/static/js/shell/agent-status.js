// Agent status poller. Reads the status URL from <body data-agent-status-url>;
// only authenticated pages render this attribute, so the module no-ops for
// anonymous visitors. Exposes window.refreshAgentStatus and dispatches an
// `agent-status` CustomEvent so other modules (e.g. chat) can react.

const url = document.body.dataset.agentStatusUrl;
const dot = document.getElementById('agent-status-dot');
const name = document.getElementById('agent-status-name');

if (url) {
    window.__agentStatus = { connected: null, name: null };

    const refresh = function () {
        fetch(url)
            .then(r => r.json())
            .then(function (d) {
                if (dot) dot.className = 'agent-status-dot ' + (d.connected ? 'is-connected' : 'is-disconnected');
                if (name) name.textContent = d.name || '—';
                window.__agentStatus = { connected: !!d.connected, name: d.name || null };
                window.dispatchEvent(new CustomEvent('agent-status', { detail: window.__agentStatus }));
            })
            .catch(function () { /* keep last-known state */ });
    };

    window.refreshAgentStatus = refresh;
    refresh();
    setInterval(refresh, 5000);
}
