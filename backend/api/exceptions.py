"""Central DRF exception handler.

Maps plain Python exceptions raised below the view layer to HTTP responses, so
handlers don't each re-wrap errors. A view (or a service it calls) can simply
``raise ValueError("bad input")`` and get a clean ``400`` instead of a ``500``:

- ``ValueError``      → 400 Bad Request
- ``LookupError``     → 404 Not Found
- ``PermissionError`` → 403 Forbidden

Everything DRF already understands (``APIException``, ``Http404``,
``PermissionDenied``, auth failures) is handled by its own default handler, which
we call first; a genuinely unmapped exception still falls through to a ``500``.

Caveat: ``LookupError`` is the base class of ``KeyError`` / ``IndexError``. This
mapping is meant for code that raises ``LookupError`` to signal a missing record —
be aware an *accidental* ``KeyError`` will therefore surface as a ``404`` rather
than a ``500``.
"""

from __future__ import annotations

from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

# None of these three are subclasses of one another, so iteration order does not
# affect correctness; it is kept most-restrictive-first only for readability.
_STATUS_BY_EXC: tuple[tuple[type[Exception], int], ...] = (
    (PermissionError, 403),
    (LookupError, 404),
    (ValueError, 400),
)


def custom_exception_handler(exc: Exception, context: Any) -> Response | None:
    """Map plain exceptions to HTTP responses, deferring to DRF otherwise."""
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    for exc_type, status_code in _STATUS_BY_EXC:
        if isinstance(exc, exc_type):
            return Response({"detail": str(exc)}, status=status_code)

    return None
