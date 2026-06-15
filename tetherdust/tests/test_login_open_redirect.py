"""Guards for the login open-redirect fix.

`portal.views.api.login_view` honors a `?next=` target after authentication.
Without validation, `/login/?next=https://evil.com` would bounce the user
off-site after a real login. The view must validate `next` with Django's
`url_has_allowed_host_and_scheme` against the current host.

These tests cover (1) the wiring — the view still calls the validator — and
(2) the validator's behaviour for the exact argument shape the view uses.
"""

import re
from pathlib import Path

from django.utils.http import url_has_allowed_host_and_scheme

API_VIEW = Path(__file__).resolve().parent.parent / "web" / "portal" / "views" / "api.py"


def test_login_view_validates_next() -> None:
    """The view imports and calls url_has_allowed_host_and_scheme on `next`."""
    src = API_VIEW.read_text(encoding="utf-8")
    assert "url_has_allowed_host_and_scheme" in src, "validator not used in login view"
    assert "allowed_hosts={request.get_host()}" in src, (
        "validator is not scoped to the request host"
    )


def test_login_view_has_no_unvalidated_next_redirect() -> None:
    """The old naive `redirect(next_url if next_url else ...)` is gone."""
    src = API_VIEW.read_text(encoding="utf-8")
    assert not re.search(r"redirect\(\s*next_url\s+if\s+next_url", src), (
        "login view still redirects to next_url without validation"
    )


# Behaviour of the validator with the view's argument shape (host-scoped).
HOST = "localhost"

REJECTED = [
    "https://evil.com",  # absolute off-site
    "http://evil.com/path",
    "//evil.com",  # scheme-relative → off-site
    "https://localhost.evil.com",  # suffix trick
    "javascript:alert(1)",  # dangerous scheme
    "\\/\\/evil.com",  # backslash bypass attempt
]

ALLOWED = [
    "/chat",
    "/docs/?open=x",
    "/control/dashboard",
]


def test_offsite_and_dangerous_next_rejected() -> None:
    for target in REJECTED:
        assert not url_has_allowed_host_and_scheme(
            target, allowed_hosts={HOST}, require_https=False
        ), f"should have rejected open-redirect target: {target!r}"


def test_local_next_allowed() -> None:
    for target in ALLOWED:
        assert url_has_allowed_host_and_scheme(target, allowed_hosts={HOST}, require_https=False), (
            f"should have allowed local target: {target!r}"
        )
