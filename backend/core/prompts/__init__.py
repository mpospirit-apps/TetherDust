"""Central home for the agent prompts that are defined in code.

Phase 1 of prompt consolidation: every developer-owned prompt that used to live
inline across ``console/views``, ``console/consumers`` and ``core/engines`` now
lives in one package, grouped by feature. Behaviour is unchanged — these are the
same strings, just under one roof.

Out of scope (admin-editable, already in the DB with a UI): the agent system
prompt (``AgentConfiguration.system_prompt``) and the ``/prompt`` chat templates
(``PromptConfiguration``).

``REGISTRY`` enumerates what lives here, keyed by a stable name, so the set of
prompts can be listed in one place (e.g. a future read-only console view).
"""

from .charts import build_chart_edit_prompt
from .dashboards import DASHBOARD_TEMPLATES
from .docs import (
    CORE_PRINCIPLES,
    DOC_TEMPLATES,
    LIBRARY_GUIDE,
    TETHERDUST_CONTEXT,
    WIKILINK_NOTE,
    build_doc_generation_prompt,
    build_library_prompt,
)
from .tethers import build_tether_prompt

__all__ = [
    "build_chart_edit_prompt",
    "DASHBOARD_TEMPLATES",
    "CORE_PRINCIPLES",
    "DOC_TEMPLATES",
    "LIBRARY_GUIDE",
    "TETHERDUST_CONTEXT",
    "WIKILINK_NOTE",
    "build_doc_generation_prompt",
    "build_library_prompt",
    "build_tether_prompt",
    "REGISTRY",
]


REGISTRY = {
    "docs.generation": {
        "description": "Single-file AI documentation generation.",
        "variants": sorted(DOC_TEMPLATES),
        "call_site": "console/views/docsource.py",
    },
    "docs.library": {
        "description": "Multi-file AI documentation library generation.",
        "variants": [],
        "call_site": "console/views/docsource.py",
    },
    "dashboards.generation": {
        "description": "AI dashboard generation.",
        "variants": sorted(DASHBOARD_TEMPLATES),
        "call_site": "console/views/dashboard.py",
    },
    "charts.edit": {
        "description": "AI chart-edit consumer (update_chart).",
        "variants": [],
        "call_site": "console/consumers/chart_edit.py",
    },
    "tethers.generation": {
        "description": "Tether code↔database graph generation.",
        "variants": [],
        "call_site": "core/engines/tether_engine.py",
    },
}
