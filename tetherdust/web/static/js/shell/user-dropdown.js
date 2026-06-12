// User dropdown — open/close behaviour for the navbar avatar menu.

const btn = document.getElementById('user-dropdown-btn');
const menu = document.getElementById('user-dropdown-menu');

if (btn && menu) {
    btn.addEventListener('click', function (e) {
        e.stopPropagation();
        menu.classList.toggle('is-open');
    });
    document.addEventListener('click', function () {
        menu.classList.remove('is-open');
    });
    menu.addEventListener('click', function (e) { e.stopPropagation(); });
}
