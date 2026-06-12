// Chat page entry. Wires together the chat modules against the DOM emitted
// by chat/templates/chat/chat.html. URLs are read from data-* attributes
// on the .chat-layout root so the bundle stays static-cacheable.

import { renderMarkdown, transformDocLinks } from './markdown-renderer.js';
import {
    addMessage,
    addTypingIndicator,
    removeTypingIndicator,
    setInlineStatus,
    renderToolsUsed,
    renderPrimitivesUsed,
    ensureCopyButton,
} from './message-render.js';
import { createMentionChipsManager } from './mention-chips.js';
import { createSlashController } from './slash-commands.js';
import { createChatSocket } from './ws-client.js';
import { createSessionUI } from './session-ui.js';

const layout = document.querySelector('.chat-layout');
if (layout && layout.dataset.docSourcesUrl) {
    init();
}

function init() {
    const docSourcesUrl = layout.dataset.docSourcesUrl;
    const promptsUrl = layout.dataset.promptsUrl;
    const sessionsUrl = layout.dataset.sessionsUrl;

    const chatMessages = document.getElementById('chat-messages');
    const chatInput = document.getElementById('chat-input');
    const chatForm = document.getElementById('chat-form');
    const chatInputContainer = document.querySelector('.chat-input-container');
    const sendButton = document.getElementById('send-button');
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    const mentionChipsContainer = document.getElementById('mention-chips');
    const mentionChips = createMentionChipsManager(mentionChipsContainer);

    const slashDropdown = document.getElementById('slash-autocomplete');
    const slashList = document.getElementById('slash-autocomplete-list');
    const slashController = createSlashController({
        inputEl: chatInput,
        listEl: slashList,
        dropdownEl: slashDropdown,
        docSourcesUrl,
        promptsUrl,
        mentionChips,
    });

    // Connection / agent state
    const connectionBanner = document.getElementById('connection-banner');
    const connectionBannerText = document.getElementById('connection-banner-text');
    let wsState = 'connecting';
    let agentConnected = (window.__agentStatus && window.__agentStatus.connected === false) ? false : true;
    let awaitingResponse = false;

    function setChatInputVisible(visible) {
        chatInputContainer.style.display = visible ? '' : 'none';
    }

    function setSendButtonMode(stop) {
        sendButton.classList.toggle('is-stop', stop);
        sendButton.setAttribute('aria-label', stop ? 'Stop generating' : 'Send message');
        sendButton.innerHTML = stop
            ? '<i class="fa-solid fa-stop"></i>'
            : '<i class="fa-solid fa-paper-plane"></i>';
    }

    function applyInputState() {
        const connectionDown = wsState !== 'connected' || agentConnected === false;
        // While awaiting a response the input is locked, but the send button
        // stays active as a Stop control so the user can cancel mid-stream.
        chatInput.disabled = awaitingResponse || connectionDown;
        sendButton.disabled = connectionDown;
        setSendButtonMode(awaitingResponse);
        chatInputContainer.classList.toggle('is-agent-down', agentConnected === false);

        let msg = null;
        if (agentConnected === false) msg = 'Agent unreachable. Contact to your admin.';
        else if (wsState === 'connecting') msg = 'Connecting to agent…';
        else if (wsState === 'reconnecting') msg = 'Reconnecting…';
        else if (wsState === 'failed') msg = 'Agent unreachable. Start a new chat to retry.';

        if (msg) {
            connectionBannerText.textContent = msg;
            connectionBanner.classList.add('is-visible');
        } else {
            connectionBanner.classList.remove('is-visible');
        }
    }

    window.addEventListener('agent-status', function (e) {
        const wasConnected = agentConnected;
        agentConnected = e.detail && e.detail.connected === true;
        applyInputState();
        if (!wasConnected && agentConnected) chatInput.focus();
    });

    // Empty / stream state
    const emptyStateHTML = chatMessages.querySelector('.chat-empty-state')?.outerHTML || '';
    function showEmptyState() { chatMessages.innerHTML = emptyStateHTML; }

    let currentSessionId = null;
    let currentStreamDiv = null;
    let currentChunks = [];

    function startNewChat() {
        currentSessionId = null;
        chatMessages.innerHTML = '';
        showEmptyState();
        setChatInputVisible(true);
        chatSocket.connect(null);
    }

    function switchSession(sessionId) {
        if (sessionId === currentSessionId) return;
        currentSessionId = sessionId;
        chatMessages.innerHTML = '';
        setChatInputVisible(false);
        chatSocket.connect(sessionId);
    }

    const sessionUI = createSessionUI({
        panel: document.getElementById('history-panel'),
        list: document.getElementById('history-list'),
        toggle: document.getElementById('history-toggle'),
        search: document.getElementById('history-search-input'),
        newChatBtn: document.getElementById('new-chat-btn'),
        sessionsUrl,
        csrfToken,
        getCurrentSessionId: () => currentSessionId,
        onSwitchSession: switchSession,
        onNewChat: startNewChat,
    });

    // Turn the live typing indicator into a finished agent message. Shared by
    // normal completion (stream_end) and cancellation (stream_cancelled).
    function finalizeStream(finalText, tools, interrupted) {
        const text = interrupted
            ? (finalText ? finalText + '\n\n*(interrupted)*' : '*(interrupted)*')
            : finalText;
        const typingEl = document.getElementById('typing-indicator');

        let streamDiv = null;
        if (typingEl && text) {
            typingEl.removeAttribute('id');
            const inlineStatusEl = typingEl.querySelector('#typing-inline-status');
            if (inlineStatusEl) {
                inlineStatusEl.style.display = 'none';
                inlineStatusEl.textContent = '';
                inlineStatusEl.removeAttribute('id');
            }
            const td = typingEl.querySelector('.message-content');
            if (td) td.className = 'message-content';
            streamDiv = typingEl;
        } else {
            removeTypingIndicator('typing-indicator');
            if (text) streamDiv = addMessage(chatMessages, '', 'agent');
        }

        if (streamDiv && text) {
            const contentDiv = streamDiv.querySelector('.message-content');
            contentDiv.innerHTML = renderMarkdown(text);
            chatMessages.scrollTop = chatMessages.scrollHeight;
            if (tools && tools.length) renderToolsUsed(streamDiv, tools);
            transformDocLinks(streamDiv);
            const bodyDiv = streamDiv.querySelector('.message-body');
            ensureCopyButton(bodyDiv, contentDiv);
        }

        setInlineStatus(null);
        currentStreamDiv = null;
        currentChunks = [];
        awaitingResponse = false;
        applyInputState();
        if (!chatInput.disabled) chatInput.focus();
    }

    function handleSocketMessage(data) {
        console.log('[DEBUG WS] received:', data.type, data);

        switch (data.type) {
            case 'session_info':
                currentSessionId = data.session_id;
                sessionUI.loadSessions();
                break;

            case 'history':
                // Re-rendered wholesale: the consumer re-sends history on every
                // (re)connect, so clear first to stay idempotent — otherwise a
                // reconnect would append a duplicate copy of every message.
                if (data.messages.length > 0) {
                    chatMessages.innerHTML = '';
                }
                data.messages.forEach(function (msg) {
                    const type = msg.role === 'user' ? 'user' : 'agent';
                    const msgDiv = addMessage(chatMessages, msg.content, type, type === 'agent');
                    if (type === 'agent' && msg.tools && msg.tools.length) {
                        renderToolsUsed(msgDiv, msg.tools);
                    }
                    if (type === 'agent') {
                        transformDocLinks(msgDiv);
                    }
                    if (type === 'user' && (msg.sources || msg.prompts)) {
                        renderPrimitivesUsed(msgDiv, msg.sources, msg.prompts);
                    }
                });
                break;

            case 'stream_start':
                currentStreamDiv = null;
                currentChunks = [];
                setInlineStatus('Thinking…');
                break;

            case 'stream_status':
                setInlineStatus(data.content);
                break;

            case 'stream_chunk':
                currentChunks.push(data.content);
                setInlineStatus(data.content);
                break;

            case 'stream_end':
                finalizeStream(
                    data.content || (currentChunks.length ? currentChunks.join('') : ''),
                    data.tools,
                    false,
                );
                sessionUI.loadSessions();
                break;

            case 'stream_cancelled':
                finalizeStream(
                    data.content || (currentChunks.length ? currentChunks.join('') : ''),
                    null,
                    true,
                );
                sessionUI.loadSessions();
                break;

            case 'error':
                removeTypingIndicator('typing-indicator');
                setInlineStatus(null);
                addMessage(chatMessages, data.message, 'agent');
                awaitingResponse = false;
                if (typeof window.refreshAgentStatus === 'function') window.refreshAgentStatus();
                applyInputState();
                if (!chatInput.disabled) chatInput.focus();
                break;
        }
    }

    const chatSocket = createChatSocket({
        getSessionId: () => currentSessionId,
        onOpen: () => slashController.reload(),
        onClose: () => setChatInputVisible(false),
        onStateChange: (state) => { wsState = state; applyInputState(); },
        onMessage: handleSocketMessage,
    });

    // Input handling
    chatInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 140) + 'px';
    });

    chatInput.addEventListener('keydown', function (e) {
        if (slashController.handleKeydown(e)) return;
        if (e.key === 'Backspace' && chatInput.selectionStart === 0 && chatInput.selectionEnd === 0) {
            if (mentionChips.removeLast()) {
                e.preventDefault();
                return;
            }
        }
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });

    window.fillInput = function (button) {
        chatInput.value = button.textContent.trim();
        chatInput.focus();
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 140) + 'px';
    };

    chatForm.addEventListener('submit', function (e) {
        e.preventDefault();

        // While a response is streaming the button acts as a Stop control.
        if (awaitingResponse) {
            if (chatSocket.isOpen()) chatSocket.send({ type: 'cancel' });
            return;
        }

        const message = chatInput.value.trim();
        if (!message) return;
        if (!chatSocket.isOpen()) return;
        if (agentConnected === false) return;

        const emptyState = chatMessages.querySelector('.chat-empty-state');
        if (emptyState) emptyState.remove();

        const userMsgDiv = addMessage(chatMessages, message, 'user');

        const resources = mentionChips.getResources();
        const prompts = mentionChips.getPrompts();
        if (resources.length > 0 || prompts.length > 0) {
            renderPrimitivesUsed(
                userMsgDiv,
                resources.map(r => ({ uri: r.uri, name: r.name })),
                prompts.map(p => ({ name: p.name, display_name: p.display_name }))
            );
        }

        chatInput.value = '';
        chatInput.style.height = 'auto';

        sendButton.classList.add('is-sending');
        sendButton.addEventListener('animationend', function () {
            sendButton.classList.remove('is-sending');
        }, { once: true });

        addTypingIndicator(chatMessages);

        awaitingResponse = true;
        applyInputState();

        const payload = { message };
        if (resources.length > 0) {
            payload.resource_uris = resources.map(r => r.uri);
            payload.sources_info = resources.map(r => ({ uri: r.uri, name: r.name }));
        }
        if (prompts.length > 0) {
            payload.prompt_context = prompts.map(p => p.content);
            payload.prompts_info = prompts.map(p => ({ name: p.name, display_name: p.display_name }));
        }
        chatSocket.send(payload);
        mentionChips.clearAll();
    });

    window.addEventListener('beforeunload', function () {
        chatSocket.closeNoReconnect();
    });

    applyInputState();
    chatSocket.connect(null);
    sessionUI.loadSessions(true);
}
