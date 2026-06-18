// Slash / mention autocomplete. Handles both `@` doc-resource lookups
// (server-side search, debounced) and `/` prompt selection (cached locally).

export function createSlashController({
    inputEl,
    listEl,
    dropdownEl,
    docSourcesUrl,
    promptsUrl,
    mentionChips,
}) {
    let slashActive = false;
    let promptActive = false;
    let slashSelectedIndex = -1;

    let docSearchTimer = null;
    let docSearchResults = [];

    let promptResources = [];
    let promptResourcesLoading = true;

    async function loadPromptResources() {
        promptResourcesLoading = true;
        try {
            const resp = await fetch(promptsUrl);
            const data = await resp.json();
            promptResources = data.prompts || [];
        } catch (err) {
            console.error('Failed to load prompts:', err);
        } finally {
            promptResourcesLoading = false;
        }
    }

    function getDocContext() {
        const pos = inputEl.selectionStart;
        const text = inputEl.value.substring(0, pos);
        const match = text.match(/(?:^|\s)@([^\s]*)$/);
        if (!match) return null;
        const partial = match[1];
        return { partial, startIndex: pos - partial.length };
    }

    function getPromptContext() {
        const pos = inputEl.selectionStart;
        const text = inputEl.value.substring(0, pos);
        const match = text.match(/(?:^|\s)\/([^\s]*)$/);
        if (!match) return null;
        const partial = match[1];
        return { partial, startIndex: pos - partial.length };
    }

    function showDropdown() {
        dropdownEl.style.display = '';
        if (!promptActive) slashActive = true;
        inputEl.setAttribute('aria-expanded', 'true');
    }

    function hideDropdown() {
        dropdownEl.style.display = 'none';
        slashActive = false;
        promptActive = false;
        slashSelectedIndex = -1;
        inputEl.setAttribute('aria-expanded', 'false');
    }

    function showLoading() {
        listEl.innerHTML = '<div class="slash-autocomplete-loading"><i class="fa-solid fa-spinner fa-spin"></i></div>';
        showDropdown();
    }

    function updateSelection() {
        const items = listEl.querySelectorAll('.slash-autocomplete-item');
        items.forEach((el, i) => el.classList.toggle('selected', i === slashSelectedIndex));
        if (items[slashSelectedIndex]) items[slashSelectedIndex].scrollIntoView({ block: 'nearest' });
    }

    function searchDocResources(query) {
        clearTimeout(docSearchTimer);
        showLoading();
        docSearchTimer = setTimeout(async () => {
            try {
                const url = docSourcesUrl + '?q=' + encodeURIComponent(query);
                const resp = await fetch(url);
                const data = await resp.json();
                docSearchResults = data.resources || [];
            } catch (err) {
                console.error('Failed to search doc resources:', err);
                docSearchResults = [];
            }
            const ctx = getDocContext();
            if (!ctx) { hideDropdown(); return; }
            if (!docSearchResults.length) { hideDropdown(); return; }
            renderDocDropdown(docSearchResults.slice(0, 20));
            showDropdown();
        }, 250);
    }

    function renderDocDropdown(filtered) {
        listEl.innerHTML = '';
        slashSelectedIndex = 0;
        filtered.forEach((res, i) => {
            const item = document.createElement('div');
            item.className = 'slash-autocomplete-item' + (i === 0 ? ' selected' : '');
            item.dataset.index = i;
            item.dataset.uri = res.uri;
            const arrow = '<span class="source-arrow"><i class="fa-solid fa-chevron-right"></i></span>';
            const pathDisplay = res.path.split('/').join(arrow);
            item.innerHTML =
                '<span class="source-name">' + res.name + '</span>' +
                '<span class="source-desc">' + res.source_name + arrow + pathDisplay + '</span>';
            item.addEventListener('mousedown', e => { e.preventDefault(); selectDocItem(res); });
            item.addEventListener('mouseenter', () => { slashSelectedIndex = i; updateSelection(); });
            listEl.appendChild(item);
        });
    }

    function renderPromptDropdown(filtered) {
        listEl.innerHTML = '';
        slashSelectedIndex = 0;
        filtered.forEach((p, i) => {
            const item = document.createElement('div');
            item.className = 'slash-autocomplete-item prompt-item' + (i === 0 ? ' selected' : '');
            item.dataset.index = i;
            item.dataset.name = p.name;
            item.innerHTML =
                '<span class="source-name">' + p.display_name + '</span>' +
                '<span class="source-desc">' + p.name + '</span>';
            item.addEventListener('mousedown', e => { e.preventDefault(); selectPromptItem(p); });
            item.addEventListener('mouseenter', () => { slashSelectedIndex = i; updateSelection(); });
            listEl.appendChild(item);
        });
    }

    function selectDocItem(res) {
        const ctx = getDocContext();
        if (!ctx) { hideDropdown(); return; }
        let triggerStart = ctx.startIndex - 1;
        if (triggerStart > 0 && inputEl.value[triggerStart - 1] === ' ') triggerStart--;
        const before = inputEl.value.substring(0, Math.max(triggerStart, 0));
        const after = inputEl.value.substring(inputEl.selectionStart);
        inputEl.value = (before + after).trim();
        inputEl.setSelectionRange(inputEl.value.length, inputEl.value.length);
        mentionChips.addResource(res);
        hideDropdown();
        inputEl.dispatchEvent(new Event('input'));
    }

    function selectPromptItem(prompt) {
        const ctx = getPromptContext();
        if (!ctx) { hideDropdown(); return; }
        let triggerStart = ctx.startIndex - 1;
        if (triggerStart > 0 && inputEl.value[triggerStart - 1] === ' ') triggerStart--;
        const before = inputEl.value.substring(0, Math.max(triggerStart, 0));
        const after = inputEl.value.substring(inputEl.selectionStart);
        inputEl.value = (before + after).trim();
        inputEl.setSelectionRange(inputEl.value.length, inputEl.value.length);
        mentionChips.addPrompt(prompt);
        hideDropdown();
        inputEl.dispatchEvent(new Event('input'));
    }

    function handleInput() {
        const promptCtx = getPromptContext();
        if (promptCtx && promptResourcesLoading) {
            showLoading();
            return;
        }
        if (promptCtx && promptResources.length) {
            const partial = promptCtx.partial.toLowerCase();
            const filtered = promptResources.filter(p =>
                p.display_name.toLowerCase().includes(partial) ||
                p.name.toLowerCase().includes(partial)
            );
            if (filtered.length) {
                promptActive = true;
                slashActive = false;
                renderPromptDropdown(filtered.slice(0, 20));
                showDropdown();
                return;
            }
        }
        promptActive = false;

        const ctx = getDocContext();
        if (!ctx) { hideDropdown(); return; }
        const partial = ctx.partial;
        if (!partial) {
            listEl.innerHTML = '<div class="slash-autocomplete-hint">Type to search docs...</div>';
            showDropdown();
            return;
        }
        searchDocResources(partial);
    }

    function handleKeydown(e) {
        if (!(slashActive || promptActive)) return false;
        const items = listEl.querySelectorAll('.slash-autocomplete-item');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            slashSelectedIndex = Math.min(slashSelectedIndex + 1, items.length - 1);
            updateSelection();
            return true;
        }
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            slashSelectedIndex = Math.max(slashSelectedIndex - 1, 0);
            updateSelection();
            return true;
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
            e.preventDefault();
            if (items[slashSelectedIndex]) {
                const el = items[slashSelectedIndex];
                if (promptActive) {
                    const p = promptResources.find(r => r.name === el.dataset.name);
                    if (p) selectPromptItem(p);
                } else {
                    const res = docSearchResults.find(r => r.uri === el.dataset.uri);
                    if (res) selectDocItem(res);
                }
            }
            return true;
        }
        if (e.key === 'Escape') {
            e.preventDefault();
            hideDropdown();
            return true;
        }
        return false;
    }

    loadPromptResources();
    inputEl.addEventListener('input', handleInput);

    return {
        handleKeydown,
        reload: loadPromptResources,
    };
}
