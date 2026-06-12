"""Tool: list_codebases — list source-code repositories the role can read."""

from ._codebase_shared import get_allowed_codebases, load_codebases


async def list_codebases() -> str:
    """List the source-code repositories (codebases) available to you. \
Use this to discover which codebases exist before browsing or reading files. \
Each codebase is a GitHub repository you can explore with get_codebase_tree, \
read_codebase_file, and search_codebase."""
    codebases = load_codebases()

    allowed = get_allowed_codebases()
    if allowed is not None:
        codebases = [cb for cb in codebases if cb.name in allowed]

    if not codebases:
        return "No codebases are configured or accessible for your role."

    lines = ["# Available Codebases\n"]
    for cb in codebases:
        lines.append(f"## {cb.name}")
        lines.append(f"**Repository:** {cb.repo_url}")
        lines.append(f"**Branch:** {cb.ref}")
        if cb.subpath:
            lines.append(f"**Subpath:** {cb.subpath}")
        if cb.cached_tree:
            lines.append(f"**Files:** {len(cb.cached_tree)} (cached)")
        lines.append("")
    return "\n".join(lines)
