"""Auth redirects to the unified login/logout pages."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


def login_view(request: HttpRequest) -> HttpResponse:
    """Redirect to unified login page."""
    next_param = request.GET.get("next", "")
    url = "/login/"
    if next_param:
        url += f"?next={next_param}"
    return redirect(url)


def logout_view(request: HttpRequest) -> HttpResponse:
    """Redirect to unified logout."""
    return redirect("portal:logout")
