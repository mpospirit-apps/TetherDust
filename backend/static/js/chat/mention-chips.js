// Mention chip manager — owns the selected resources / prompts state for
// the chat input and renders chips into a host container.

export function createMentionChipsManager(container) {
    let selectedResources = []; // [{uri, source_name, path, name}]
    let selectedPrompts = [];   // [{name, display_name, description, content}]

    function addChip(type, id, label) {
        const chip = document.createElement('span');
        chip.className = 'mention-chip mention-chip-' + type;
        chip.dataset.type = type;
        chip.dataset.id = id;
        chip.innerHTML =
            '<span class="mention-chip-prefix">' + (type === 'doc' ? '@' : '/') + '</span>' +
            '<span class="mention-chip-label"></span>' +
            '<button type="button" class="mention-chip-remove" tabindex="-1">&times;</button>';
        // Label via textContent — may be an agent-created doc-source name.
        chip.querySelector('.mention-chip-label').textContent = label;
        chip.querySelector('.mention-chip-remove').addEventListener('click', function () {
            removeChip(type, id);
        });
        container.appendChild(chip);
    }

    function removeChip(type, id) {
        if (type === 'doc') {
            selectedResources = selectedResources.filter(r => r.uri !== id);
        } else {
            selectedPrompts = selectedPrompts.filter(p => p.name !== id);
        }
        const chip = container.querySelector(
            '.mention-chip[data-type="' + type + '"][data-id="' + id + '"]'
        );
        if (chip) chip.remove();
    }

    function removeLast() {
        const chips = container.querySelectorAll('.mention-chip');
        if (!chips.length) return false;
        const last = chips[chips.length - 1];
        removeChip(last.dataset.type, last.dataset.id);
        return true;
    }

    function clearAll() {
        selectedResources = [];
        selectedPrompts = [];
        container.innerHTML = '';
    }

    function addResource(res) {
        if (!selectedResources.some(r => r.uri === res.uri)) {
            selectedResources.push(res);
            addChip('doc', res.uri, res.name);
        }
    }

    function addPrompt(prompt) {
        if (!selectedPrompts.some(p => p.name === prompt.name)) {
            selectedPrompts.push(prompt);
            addChip('prompt', prompt.name, prompt.display_name);
        }
    }

    return {
        removeLast,
        clearAll,
        addResource,
        addPrompt,
        getResources: () => selectedResources,
        getPrompts: () => selectedPrompts,
    };
}
