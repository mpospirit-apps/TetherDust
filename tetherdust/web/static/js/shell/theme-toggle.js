// Theme toggle: light/dark via #theme-toggle-btn. Also swaps the highlight.js
// stylesheet (only present on chat/base.html — admin doesn't load hljs).
// Auto-wires on import; bails if nothing to do.

const btn = document.getElementById('theme-toggle-btn');
const icon = document.getElementById('theme-icon');
const label = document.getElementById('theme-label');
const hljsTheme = document.getElementById('hljs-theme');
const hljsBase = 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/';

function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('td-theme', t);
    if (icon) icon.className = t === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
    if (label) label.textContent = t === 'dark' ? 'Light mode' : 'Dark mode';
    if (hljsTheme) hljsTheme.href = hljsBase + (t === 'dark' ? 'github-dark.min.css' : 'github.min.css');
}

applyTheme(document.documentElement.getAttribute('data-theme') || 'light');

if (btn) {
    btn.addEventListener('click', function () {
        const current = document.documentElement.getAttribute('data-theme');
        applyTheme(current === 'dark' ? 'light' : 'dark');
    });
}
