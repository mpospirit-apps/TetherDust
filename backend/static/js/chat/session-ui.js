// History sidebar — session list, search, context-menu delete.

const GROUP_COLORS = [
    'var(--c-cyan)',
    'var(--c-lime)',
    'var(--c-pink)',
    'var(--c-orange)',
    'var(--c-red)',
];

export function createSessionUI({
    panel,
    list,
    toggle,
    search,
    newChatBtn,
    sessionsUrl,
    csrfToken,
    getCurrentSessionId,
    onSwitchSession,
    onNewChat,
}) {
    let allSessions = [];
    let sessionsInitialLoad = true;
    let activeContextMenu = null;

    toggle.addEventListener('click', () => panel.classList.toggle('collapsed'));
    newChatBtn.addEventListener('click', () => onNewChat());

    search.addEventListener('input', function () {
        const query = this.value.trim().toLowerCase();
        if (!query) { renderSessions(allSessions); return; }
        const filtered = allSessions.filter(s => s.title.toLowerCase().includes(query));
        renderSessions(filtered);
    });

    document.addEventListener('click', removeContextMenu);

    function removeContextMenu() {
        if (activeContextMenu) {
            activeContextMenu.remove();
            activeContextMenu = null;
        }
    }

    function showContextMenu(e, session) {
        removeContextMenu();
        const menu = document.createElement('div');
        menu.className = 'history-context-menu';
        menu.style.left = e.pageX + 'px';
        menu.style.top = e.pageY + 'px';

        const deleteBtn = document.createElement('button');
        deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i> Delete';
        deleteBtn.className = 'danger';
        deleteBtn.addEventListener('click', function (ev) {
            ev.stopPropagation();
            removeContextMenu();
            deleteSession(session.id);
        });
        menu.appendChild(deleteBtn);

        document.body.appendChild(menu);
        activeContextMenu = menu;
    }

    async function loadSessions(showSpinner = false) {
        if (showSpinner) {
            list.innerHTML = '<div class="docs-loading"><div class="typing-dots"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div>';
        }
        try {
            const resp = await fetch(sessionsUrl);
            const data = await resp.json();
            allSessions = data.sessions;
            renderSessions(allSessions);
        } catch (err) {
            console.error('Failed to load sessions:', err);
        }
    }

    function renderSessions(sessions) {
        list.innerHTML = '';
        if (sessions.length === 0) {
            list.innerHTML = '<div class="history-empty">No conversations yet</div>';
            return;
        }

        const seenGroups = new Set();
        const orderedGroups = [];
        for (const s of sessions) {
            if (!seenGroups.has(s.group)) {
                seenGroups.add(s.group);
                orderedGroups.push(s.group);
            }
        }

        const currentSessionId = getCurrentSessionId();
        let itemIndex = 0;
        orderedGroups.forEach((group, idx) => {
            const items = sessions.filter(s => s.group === group);

            const label = document.createElement('div');
            label.className = 'history-section-label';
            label.textContent = group;
            label.style.color = GROUP_COLORS[idx % GROUP_COLORS.length];
            list.appendChild(label);

            for (const session of items) {
                const btn = document.createElement('button');
                btn.className = sessionsInitialLoad ? 'history-item animate-in' : 'history-item';
                if (sessionsInitialLoad) btn.style.animationDelay = Math.min(itemIndex * 28, 280) + 'ms';
                itemIndex++;
                if (session.id === currentSessionId) btn.classList.add('active');
                btn.dataset.sessionId = session.id;

                const isActive = session.id === currentSessionId;
                const iconClass = isActive ? 'fa-solid fa-message' : 'fa-regular fa-message';

                btn.innerHTML = `<i class="${iconClass}"></i><span></span>`;
                btn.querySelector('span').textContent = session.title;

                btn.addEventListener('click', () => onSwitchSession(session.id));
                btn.addEventListener('contextmenu', function (e) {
                    e.preventDefault();
                    showContextMenu(e, session);
                });

                list.appendChild(btn);
            }
        });

        sessionsInitialLoad = false;
    }

    async function deleteSession(sessionId) {
        // Optimistic removal
        const sessionBtn = list.querySelector(`[data-session-id="${sessionId}"]`);
        if (sessionBtn) sessionBtn.remove();
        try {
            await fetch(`/chat/sessions/${sessionId}/`, {
                method: 'DELETE',
                headers: { 'X-CSRFToken': csrfToken },
            });
            if (sessionId === getCurrentSessionId()) {
                onNewChat();
            }
            loadSessions();
        } catch (err) {
            console.error('Failed to delete session:', err);
            loadSessions();
        }
    }

    return { loadSessions };
}
