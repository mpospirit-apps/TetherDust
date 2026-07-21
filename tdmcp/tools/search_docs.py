"""Tool: search_docs — semantic search across markdown documentation.

Uses the ccc (cocoindex-code) service for embeddings-based search when it is
configured, mirroring ``search_codebase``. Each documentation source folder
(``sources/docs/<folder>``) is its own ccc project, so we only search the folders
the current role is allowed to see. When ccc is unavailable (``CCC_SERVICE_URL``
unset or the service is down / a folder is not indexed yet) we fall back to the
in-process keyword search in ``DocumentationParser.search_docs``.
"""

import asyncio
import logging
from typing import Annotated

from pydantic import Field

from ..utils.markdown_parser import DocumentationParser
from . import _ccc_client, get_shared_parser
from ._db_shared import get_allowed_doc_sources

logger = logging.getLogger(__name__)


def _hit_score(hit: dict[str, object]) -> float:
    score = hit.get("score")
    return float(score) if isinstance(score, int | float) else 0.0


def ccc_project(folder: str) -> str:
    """The ccc project path for a documentation source folder.

    Kept in sync with the backend's ``DocSourceService.ccc_project`` so search
    hits resolve against the same root the indexer builds.
    """
    return "sources/docs/" + folder.strip("/")


def _keyword_search(
    parser: DocumentationParser, query: str, allowed_sources: set[str] | None
) -> str:
    """The original in-process keyword search (fallback when ccc is unavailable)."""
    results = parser.search_docs(query)
    if allowed_sources is not None:
        results = [r for r in results if r.source_name in allowed_sources]

    if not results:
        return f"No documentation found matching '{query}'. Try different search terms."

    lines = [f"# Search Results for: {query}\n"]
    for i, result in enumerate(results, 1):
        lines.append(f"## Result {i}: {result.heading or 'Untitled'}")
        lines.append(f"*Source: {result.source_file}* (relevance: {result.relevance_score:.0%})\n")
        lines.append(result.content)
        lines.append("")
    return "\n".join(lines)


def _format_semantic_results(query: str, hits: list[tuple[str, dict[str, object]]]) -> str:
    """Format merged ccc hits (already sorted, capped) as markdown.

    Each entry is ``(folder, hit)`` where *hit* is ``{path, lines, lang, score,
    snippet}`` from the ccc service.
    """
    lines = [f"# Search Results for: {query}\n"]
    for i, (folder, hit) in enumerate(hits, 1):
        path = str(hit.get("path", ""))
        rng = hit.get("lines")
        source = f"{folder}/{path}" + (f":{rng}" if rng else "")
        score = hit.get("score")
        score_str = f"{score:.2f}" if isinstance(score, int | float) else "?"
        lines.append(f"## Result {i}")
        lines.append(f"*Source: {source}* (score: {score_str})\n")
        snippet = str(hit.get("snippet") or "").strip()
        if snippet:
            lines.append(snippet)
        lines.append("")
    return "\n".join(lines)


async def search_docs(
    query: Annotated[str, Field(description="Natural language search query")],
) -> str:
    """Search the documentation for information about data flows, business logic, \
relationships between tables, and system architecture. Use this tool when \
the user asks 'how does X work', 'what is the flow for Y', or needs \
conceptual understanding rather than raw data. Returns relevant sections \
from markdown documentation including mermaid diagrams and explanations."""
    if not query or not query.strip():
        return "Error: query parameter is required"

    parser = get_shared_parser()
    allowed_sources = get_allowed_doc_sources()

    if _ccc_client.is_configured():
        semantic = await _semantic_search(parser, query, allowed_sources)
        if semantic is not None:
            return semantic
        logger.info("[search_docs] ccc search unavailable, falling back to keyword search")

    return _keyword_search(parser, query, allowed_sources)


async def _semantic_search(
    parser: DocumentationParser, query: str, allowed_sources: set[str] | None
) -> str | None:
    """Run ccc search across the allowed doc folders.

    Returns formatted markdown (results or a "no results" message) when at least
    one folder searched successfully, or ``None`` to signal the caller to fall
    back to keyword search (ccc configured but every folder errored / unindexed).
    """
    parser._ensure_loaded()
    source_names = {s.name for s in parser._sources}
    if allowed_sources is not None:
        folders = sorted(source_names & allowed_sources)
    else:
        folders = sorted(source_names)

    if not folders:
        return f"No documentation found matching '{query}'. Try different search terms."

    async def _one(folder: str) -> tuple[str, list[dict[str, object]]] | None:
        try:
            return folder, await asyncio.to_thread(
                _ccc_client.search, ccc_project(folder), query, 10
            )
        except _ccc_client.CccError as exc:
            logger.info("[search_docs] ccc search skipped folder %r: %s", folder, exc)
            return None
        except Exception:
            logger.exception("[search_docs] unexpected error searching folder %r", folder)
            return None

    outcomes = await asyncio.gather(*[_one(f) for f in folders])
    if all(o is None for o in outcomes):
        return None  # every folder failed — let the caller fall back to keyword

    hits: list[tuple[str, dict[str, object]]] = []
    for outcome in outcomes:
        if outcome is None:
            continue
        folder, folder_hits = outcome
        hits.extend((folder, h) for h in folder_hits)

    if not hits:
        return f"No documentation found matching '{query}'. Try different search terms."

    hits.sort(key=lambda fh: _hit_score(fh[1]), reverse=True)
    return _format_semantic_results(query, hits[:10])
