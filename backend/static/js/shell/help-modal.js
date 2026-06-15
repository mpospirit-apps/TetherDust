// Help modal triggers — admin pages drop [data-help-open="<id>"] / [data-help-close]
// onto buttons. Single delegated listener on document; Esc closes any open modal.

document.addEventListener('click', function (e) {
    const opener = e.target.closest('[data-help-open]');
    if (opener) {
        const target = document.getElementById(opener.dataset.helpOpen);
        if (target) target.classList.add('is-open');
        return;
    }
    const closer = e.target.closest('[data-help-close]');
    if (closer) {
        const modal = closer.closest('.help-modal');
        if (modal) modal.classList.remove('is-open');
        return;
    }
    if (e.target.classList.contains('help-modal')) {
        e.target.classList.remove('is-open');
    }
});

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        document.querySelectorAll('.help-modal.is-open').forEach(m => m.classList.remove('is-open'));
    }
});
