// Markdown renderer + link transforms. Depends on the global `marked` and
// `hljs` loaded by chat/base.html.

const renderer = new marked.Renderer();
const defaultLinkRenderer = renderer.link.bind(renderer);
renderer.link = function (token) {
    const href = token.href || '';
    // Strip relative .md links — the agent generates these but they
    // don't resolve in the chat UI. Keep the text as a styled span.
    if (href && !href.startsWith('http') && !href.startsWith('docs://') && /\.md$/i.test(href)) {
        const text = token.text || href.replace(/\.md$/i, '');
        return '<span class="chat-doc-ref"><i class="fa-regular fa-file-lines"></i> ' + text + '</span>';
    }
    return defaultLinkRenderer(token);
};

marked.setOptions({
    renderer,
    highlight: function (code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            return hljs.highlight(code, { language: lang }).value;
        }
        return hljs.highlightAuto(code).value;
    },
    breaks: true,
    gfm: true,
});

// DOMPurify config: the upstream-default URI allow-list plus the custom `docs:`
// scheme (chat doc references), which is inert/non-executable. Everything else
// stays at DOMPurify defaults — <script>, event-handler attributes, and
// javascript:/data: URLs are stripped. This closes the stored-XSS vector where
// untrusted database/documentation content echoed into an agent answer would
// otherwise be parsed as live HTML by innerHTML.
const SANITIZE_CONFIG = {
    ALLOWED_URI_REGEXP:
        /^(?:(?:(?:f|ht)tps?|mailto|tel|callto|sms|cid|xmpp|docs):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i,
};

export function renderMarkdown(raw) {
    return DOMPurify.sanitize(marked.parse(raw), SANITIZE_CONFIG);
}

export function transformDocLinks(msgDiv) {
    const contentEl = msgDiv.querySelector('.message-content');
    if (!contentEl) return;
    contentEl.innerHTML = contentEl.innerHTML.replace(
        /docs:\/\/([^\r\n<>"']+)/g,
        function (_match, path) {
            path = path.trim();
            const fileName = path.split('/').pop().replace(/\.md$/i, '');
            const url = '/docs/?open=' + encodeURIComponent(path);
            return '<a href="' + url + '" target="_blank" class="chat-doc-link" title="' + path + '">'
                 + '<i class="fa-regular fa-file-lines"></i> ' + fileName + '</a>';
        }
    );
}
