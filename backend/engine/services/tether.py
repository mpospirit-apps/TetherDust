"""Tether read-side helpers.

Holds the display logic that used to live on the ``Tether`` model as computed
properties. Reached via the ``get`` registry: ``get(TetherService).source_name(t)``.
"""

from __future__ import annotations

from ..models.tethers import Tether


class TetherService:
    """Formatting helpers for :class:`Tether` (formerly model properties)."""

    def source_name(self, tether: Tether) -> str:
        """Display name of the code side, whichever source type is set.

        Callers should ``select_related("codebase", "codebase_doc_source")`` to
        avoid a per-tether query (both existing call sites already do).
        """
        if tether.codebase is not None:
            return tether.codebase.name
        if tether.codebase_doc_source is not None:
            return tether.codebase_doc_source.folder_name
        return ""
