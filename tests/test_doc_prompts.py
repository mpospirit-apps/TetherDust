"""Tests for the documentation-generation prompt builders.

``engine/prompts/docs.py`` composes prompts from three layers — the shared
``CORE_PRINCIPLES`` and ``TETHERDUST_CONTEXT``, plus a task layer that differs
between single-file generation (a lean per-type template) and library
generation (the ``LIBRARY_GUIDE`` playbook). These tests pin that layering so
the single-file prompt never inherits the multi-page scaffolding, and so the
TetherDust-specific facts the agent needs (its tools, mermaid/wiki-link
rendering, and the create_documentation save step) stay present.

The module is pure strings/functions with no Django imports, so it imports
directly without any settings setup.
"""

import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from engine.prompts.docs import (  # noqa: E402
    CORE_PRINCIPLES,
    DATABASE_LIBRARY_GUIDE,
    DOC_TEMPLATES,
    LIBRARY_GUIDE,
    TETHERDUST_CONTEXT,
    build_doc_generation_prompt,
    build_library_prompt,
)

# --- single-file generation -------------------------------------------------


def test_single_file_layers_principles_and_context_before_template() -> None:
    prompt = build_doc_generation_prompt("architecture", [])

    assert prompt.startswith(CORE_PRINCIPLES)
    assert TETHERDUST_CONTEXT in prompt
    # The chosen per-type template text is present...
    assert DOC_TEMPLATES["architecture"] in prompt
    # ...and the principles/context come before it.
    assert prompt.index(CORE_PRINCIPLES) < prompt.index(TETHERDUST_CONTEXT)
    assert prompt.index(TETHERDUST_CONTEXT) < prompt.index(DOC_TEMPLATES["architecture"])


def test_single_file_excludes_library_scaffolding() -> None:
    """The multi-page playbook must never leak into single-file prompts."""
    prompt = build_doc_generation_prompt("database_table", [])

    assert LIBRARY_GUIDE not in prompt
    assert "deep-dive" not in prompt.lower()


def test_single_file_unknown_doc_type_falls_back_to_database_table() -> None:
    prompt = build_doc_generation_prompt("not_a_real_type", [])

    assert DOC_TEMPLATES["database_table"] in prompt


def test_single_file_appends_source_material_when_given() -> None:
    without = build_doc_generation_prompt("query_examples", [])
    with_src = build_doc_generation_prompt("query_examples", ["SCHEMA DUMP X"])

    assert "Source material" not in without
    assert "Source material" in with_src
    assert "SCHEMA DUMP X" in with_src


def test_single_file_scope_embedded_when_given() -> None:
    prompt = build_doc_generation_prompt("architecture", [], scope="Focus on auth flow")

    assert "Scope and goals:" in prompt
    assert "Focus on auth flow" in prompt


def test_single_file_blank_scope_omitted() -> None:
    prompt = build_doc_generation_prompt("architecture", [], scope="   ")

    assert "Scope and goals:" not in prompt


# --- library generation -----------------------------------------------------


def test_library_includes_all_three_layers_in_order() -> None:
    prompt = build_library_prompt("My Lib")

    assert prompt.startswith(CORE_PRINCIPLES)
    assert TETHERDUST_CONTEXT in prompt
    assert LIBRARY_GUIDE in prompt
    assert (
        prompt.index(CORE_PRINCIPLES)
        < prompt.index(TETHERDUST_CONTEXT)
        < prompt.index(LIBRARY_GUIDE)
    )


def test_library_embeds_name() -> None:
    prompt = build_library_prompt("Billing Docs")

    assert "Billing Docs" in prompt


def test_database_library_uses_database_guide_not_codebase_playbook() -> None:
    prompt = build_library_prompt("Orders", "database")

    # Shared layers stay; the task guide is swapped for the table-oriented one.
    assert prompt.startswith(CORE_PRINCIPLES)
    assert TETHERDUST_CONTEXT in prompt
    assert DATABASE_LIBRARY_GUIDE in prompt
    assert LIBRARY_GUIDE not in prompt
    assert "Orders" in prompt
    # Fixed structure: Architecture.md overview + Tables/<TableName>.md pages.
    assert "Architecture.md" in prompt
    assert "Tables/<TableName>.md" in prompt


def test_codebase_library_keeps_subsystem_playbook() -> None:
    prompt = build_library_prompt("MyLib", "codebase")

    assert LIBRARY_GUIDE in prompt
    assert DATABASE_LIBRARY_GUIDE not in prompt


def test_database_guide_is_domain_agnostic() -> None:
    """The guide is general purpose — no FinTech or fixed tech-stack assumptions leak in."""
    for term in (
        "Wallet",
        "Cashflow",
        "open banking",
        "NServiceBus",
        "Hangfire",
        "ASP.NET",
        "CardInquiry",
        "MoneyTransaction",
    ):
        assert term not in DATABASE_LIBRARY_GUIDE


# --- shared content guarantees ---------------------------------------------


def test_both_modes_share_identical_principles_and_context() -> None:
    single = build_doc_generation_prompt("architecture", [])
    library = build_library_prompt("Lib")

    for shared in (CORE_PRINCIPLES, TETHERDUST_CONTEXT):
        assert shared in single
        assert shared in library


def test_context_names_tetherdust_tools_and_rendering() -> None:
    """The agent must learn its actual tools, how output renders, and how to save."""
    assert "create_documentation" in TETHERDUST_CONTEXT
    assert "mermaid" in TETHERDUST_CONTEXT
    assert "[[Folder/Page.md|Display Text]]" in TETHERDUST_CONTEXT
    for tool in ("list_codebases", "get_codebase_tree", "search_docs", "query_database"):
        assert tool in TETHERDUST_CONTEXT


def test_citation_guidance_is_anti_pinning() -> None:
    """TetherDust has no git access; the guidance must steer away from commit pins."""
    # The only mentions of pinning are explicit negations telling the agent not to.
    # (Match line-break-tolerant fragments rather than the full wrapped sentence.)
    assert "no git history or commit hash" in TETHERDUST_CONTEXT
    assert "pin to commits" in TETHERDUST_CONTEXT
    assert "do not" in " ".join(TETHERDUST_CONTEXT.split())
    # Citations are framed around what the agent actually read instead.
    assert "database -> table -> column" in " ".join(LIBRARY_GUIDE.split())
