import { renderMarkdown } from './markdown-renderer.js';

function attachCopyButton(bodyDiv, contentDiv) {
    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.title = 'Copy message';
    copyBtn.innerHTML = '<i class="fa-regular fa-copy"></i><span class="copy-label">Copy</span>';
    copyBtn.addEventListener('click', function () {
        const text = contentDiv.innerText;
        navigator.clipboard.writeText(text).then(function () {
            copyBtn.classList.add('is-confirmed');
            copyBtn.innerHTML = '<i class="fa-solid fa-check"></i><span class="copy-label">Copied!</span>';
            copyBtn.addEventListener('animationend', function () {
                copyBtn.classList.remove('is-confirmed');
            }, { once: true });
            setTimeout(function () {
                copyBtn.innerHTML = '<i class="fa-regular fa-copy"></i><span class="copy-label">Copy</span>';
            }, 1500);
        });
    });
    bodyDiv.appendChild(copyBtn);
    return copyBtn;
}

export function addMessage(chatMessages, content, type, useMarkdown) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.innerHTML = type === 'user'
        ? '<i class="fa-solid fa-user"></i>'
        : '<i class="fa-solid fa-robot"></i>';

    const bodyDiv = document.createElement('div');
    bodyDiv.className = 'message-body';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    if (useMarkdown && content) {
        contentDiv.innerHTML = renderMarkdown(content);
    } else {
        contentDiv.textContent = content;
    }

    bodyDiv.appendChild(contentDiv);
    attachCopyButton(bodyDiv, contentDiv);

    messageDiv.appendChild(avatar);
    messageDiv.appendChild(bodyDiv);

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    return messageDiv;
}

export function addTypingIndicator(chatMessages) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message agent';
    messageDiv.id = 'typing-indicator';

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.innerHTML = '<i class="fa-solid fa-robot"></i>';

    const bodyDiv = document.createElement('div');
    bodyDiv.className = 'message-body';

    const typingDiv = document.createElement('div');
    typingDiv.className = 'message-content typing-indicator';
    typingDiv.innerHTML = '<div class="typing-dots"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';

    const inlineStatus = document.createElement('div');
    inlineStatus.id = 'typing-inline-status';
    inlineStatus.style.cssText = 'display:none;padding:6px 2px 0;font-size:var(--text-xs);color:var(--text-muted);text-align:left;transition:opacity 0.2s ease;';

    bodyDiv.appendChild(typingDiv);
    bodyDiv.appendChild(inlineStatus);
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(bodyDiv);

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

export function removeTypingIndicator(id) {
    const indicator = document.getElementById(id);
    if (indicator) indicator.remove();
}

export function setInlineStatus(text) {
    const el = document.getElementById('typing-inline-status');
    if (!el) return;
    if (!text) {
        el.style.display = 'none';
        el.textContent = '';
        return;
    }
    el.style.display = '';
    el.style.opacity = '0';
    setTimeout(function () {
        el.textContent = text;
        el.style.opacity = '1';
    }, 200);
}

export function toolDisplayName(toolName) {
    return toolName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export function renderToolsUsed(messageDiv, toolNames) {
    if (!toolNames || !toolNames.length) return;
    const bodyDiv = messageDiv.querySelector('.message-body');
    if (!bodyDiv) return;

    let container = bodyDiv.querySelector('.tools-used');
    if (!container) {
        container = document.createElement('div');
        container.className = 'tools-used';
        bodyDiv.insertBefore(container, bodyDiv.firstChild);
    }

    let pillIndex = container.querySelectorAll('.tool-pill').length;
    for (const name of toolNames) {
        if (container.querySelector(`[data-tool="${name}"]`)) continue;
        const pill = document.createElement('span');
        pill.className = 'tool-pill';
        pill.dataset.tool = name;
        pill.style.setProperty('--pill-i', pillIndex++);
        pill.innerHTML = `<i class="fa-solid fa-wrench"></i><span>${toolDisplayName(name)}</span>`;
        container.appendChild(pill);
    }
}

export function renderPrimitivesUsed(messageDiv, sources, prompts) {
    if ((!sources || !sources.length) && (!prompts || !prompts.length)) return;
    const bodyDiv = messageDiv.querySelector('.message-body');
    if (!bodyDiv) return;

    let container = bodyDiv.querySelector('.primitives-used');
    if (!container) {
        container = document.createElement('div');
        container.className = 'primitives-used';
        bodyDiv.insertBefore(container, bodyDiv.firstChild);
    }

    let pillIndex = 0;
    for (const src of (sources || [])) {
        const chip = document.createElement('span');
        chip.className = 'mention-chip mention-chip-doc';
        chip.style.setProperty('--pill-i', pillIndex++);
        // Label via textContent — the name can originate from an agent-created
        // doc-source folder, so it must never be parsed as HTML.
        chip.innerHTML = '<span class="mention-chip-prefix">@</span><span class="mention-chip-label"></span>';
        chip.querySelector('.mention-chip-label').textContent = src.name;
        container.appendChild(chip);
    }
    for (const prompt of (prompts || [])) {
        const chip = document.createElement('span');
        chip.className = 'mention-chip mention-chip-prompt';
        chip.style.setProperty('--pill-i', pillIndex++);
        chip.innerHTML = '<span class="mention-chip-prefix">/</span><span class="mention-chip-label"></span>';
        chip.querySelector('.mention-chip-label').textContent = prompt.display_name;
        container.appendChild(chip);
    }
}

export function ensureCopyButton(bodyDiv, contentDiv) {
    if (bodyDiv && !bodyDiv.querySelector('.copy-btn')) {
        attachCopyButton(bodyDiv, contentDiv);
    }
}
