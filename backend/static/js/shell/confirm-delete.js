// Delete-form confirmation modal. Forms with `data-confirm="<message>"` get
// intercepted on submit and routed through #confirm-modal. Looks for these
// elements in the page (rendered by chat/admin/base.html); bails if absent.

const modal = document.getElementById('confirm-modal');
const message = document.getElementById('confirm-modal-message');
const okBtn = document.getElementById('confirm-modal-ok');
const cancelBtn = document.getElementById('confirm-modal-cancel');

if (modal && message && okBtn && cancelBtn) {
    let pendingForm = null;

    function close() {
        modal.classList.remove('is-open');
        pendingForm = null;
    }

    document.addEventListener('submit', function (e) {
        const form = e.target.closest('form[data-confirm]');
        if (!form) return;
        e.preventDefault();
        pendingForm = form;
        message.textContent = form.dataset.confirm;
        modal.classList.add('is-open');
    });

    okBtn.addEventListener('click', function () {
        if (pendingForm) {
            pendingForm.removeAttribute('data-confirm');
            pendingForm.submit();
        }
        close();
    });

    cancelBtn.addEventListener('click', close);
    modal.addEventListener('click', function (e) { if (e.target === modal) close(); });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') close();
    });
}
