"""Tool: search_docs — full-text search across markdown documentation."""

import logging
from typing import Annotated

from pydantic import Field

from . import get_shared_parser
from ._db_shared import get_allowed_doc_sources

logger = logging.getLogger(__name__)


async def search_docs(
    query: Annotated[str, Field(description="Natural language search query")],
) -> str:
    """Search the documentation for information about data flows, business logic, \
relationships between tables, and system architecture. Use this tool when \
the user asks 'how does X work', 'what is the flow for Y', or needs \
conceptual understanding rather than raw data. Returns relevant sections \
from markdown documentation including mermaid diagrams and explanations."""
    parser = get_shared_parser()
    logger.info("[DEBUG SEARCH] search_docs called with query=%r", query)
    logger.info(
        "[DEBUG SEARCH] parser sources (before load): %s",
        [s.name for s in parser._sources],
    )
    logger.info(
        "[DEBUG SEARCH] parser tables cached: %d, examples cached: %d",
        len(parser._table_cache),
        len(parser._examples_cache),
    )

    if not query:
        return "Error: query parameter is required"

    results = parser.search_docs(query)
    logger.info("[DEBUG SEARCH] raw results count: %d", len(results))
    for i, r in enumerate(results[:5]):
        logger.info(
            "[DEBUG SEARCH]   result[%d]: source=%s, heading=%s, score=%.2f",
            i,
            r.source_name,
            r.heading,
            r.relevance_score,
        )

    allowed_sources = get_allowed_doc_sources()
    logger.info("[DEBUG SEARCH] allowed_doc_sources filter: %s", allowed_sources)
    if allowed_sources is not None:
        before = len(results)
        results = [r for r in results if r.source_name in allowed_sources]
        logger.info(
            "[DEBUG SEARCH] after doc_sources filter: %d → %d results", before, len(results)
        )

    if not results:
        logger.info("[DEBUG SEARCH] NO RESULTS for query=%r", query)
        return f"No documentation found matching '{query}'. Try different search terms."

    # Format results
    lines = [f"# Search Results for: {query}\n"]

    for i, result in enumerate(results, 1):
        lines.append(f"## Result {i}: {result.heading or 'Untitled'}")
        lines.append(f"*Source: {result.source_file}* (relevance: {result.relevance_score:.0%})\n")
        lines.append(result.content)
        lines.append("")

    return "\n".join(lines)
