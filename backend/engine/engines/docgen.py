"""AI documentation generation orchestration (single-file + multi-file library).

Ported out of the legacy ``management/views/docsource.py`` so the API layer
(``api/v1/admin/docsources.py``) can drive generation without the to-be-deleted
view module. The agent runs in a background thread, streaming status into a
``DocGenerationLog`` the SPA polls via ``status_payload``.

Generation always uses the *active* agent (``get_agent()``); the ``agent_config``
passed in is recorded on the log for audit, mirroring the legacy behaviour.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, TypedDict

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from engine.models import (
    AgentConfiguration,
    DocGenerationLog,
    DocumentationSource,
    ToolConfiguration,
)
from engine.prompts import build_doc_generation_prompt, build_library_prompt
from engine.services import DocSourceService, SystemConfigService, get

logger = logging.getLogger(__name__)

# Library generation is restricted to these two source categories.
LIBRARY_DOC_TYPES = (
    DocumentationSource.DocType.DATABASE,
    DocumentationSource.DocType.CODEBASE,
)


class _LibraryFile(TypedDict):
    path: str
    size: int


# ── Config helpers ───────────────────────────────────────────────────────────


def _get_docgen_timeout() -> float:
    val = get(SystemConfigService).get_value("docgen_timeout", None)
    if val is not None:
        return float(val)
    return float(os.getenv("DOCGEN_TIMEOUT", "1800"))


def _get_doclibgen_timeout() -> float:
    """Timeout for AI library generation (longer than single-file docgen)."""
    val = get(SystemConfigService).get_value("doclibgen_timeout", None)
    if val is not None:
        return float(val)
    return float(os.getenv("DOCLIBGEN_TIMEOUT", "3600"))


def _parse_docgen_result(result_text: str) -> list[dict[str, object]]:
    """Best-effort extraction of structured errors from MCP tool return."""
    errors: list[dict[str, object]] = []
    for line in result_text.splitlines():
        line = line.strip()
        if line.startswith("- Errors:"):
            try:
                errors = json.loads(line[len("- Errors:") :].strip())
            except (json.JSONDecodeError, ValueError):
                pass
    return errors


def top_level_folders() -> list[str]:
    """Top-level folder names inside the documentations/ directory."""
    docs_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR)
    folders: list[str] = []
    if docs_dir.exists() and docs_dir.is_dir():
        for entry in sorted(docs_dir.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                folders.append(entry.name)
    return folders


def nested_folders() -> list[str]:
    """All (nested) folder paths under documentations/, for the destination picker."""
    docs_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR)
    dest_folders: list[str] = []
    if docs_dir.exists() and docs_dir.is_dir():
        for dirpath in sorted(docs_dir.rglob("*")):
            if dirpath.is_dir() and not any(
                p.startswith(".") for p in dirpath.relative_to(docs_dir).parts
            ):
                dest_folders.append(str(dirpath.relative_to(docs_dir)))
    return dest_folders


# ── Agent execution ──────────────────────────────────────────────────────────


def _execute_docgen(
    log_pk: str,
    prompt: str,
    user_id: int,
    enabled_tools: list[str],
    selected_db_names: list[str],
    selected_doc_names: list[str],
    session_id: str,
    timeout: float,
    selected_codebase_names: list[str] | None = None,
) -> str:
    """Run the agent for a docgen log, streaming status into agent_output.

    Returns the final response text. Raises on agent failure (callers mark the
    log as failed). Shared by single-file and library generation.
    """
    from engine.agents import get_agent
    from engine.agents.stream import parse_chunk, tool_status_label

    agent = get_agent()
    docgen_timeout = timeout

    async def _generate() -> str:
        chunks = []
        completed_response = ""
        async for chunk in agent.chat(
            message=prompt,
            user_id=user_id,
            session_id=session_id,
            allowed_tools=enabled_tools or None,
            allowed_databases=selected_db_names,
            allowed_doc_sources=selected_doc_names,
            allowed_codebases=selected_codebase_names,
            timeout=docgen_timeout,
        ):
            event = parse_chunk(chunk)
            if event.kind == "tool":
                status = tool_status_label(event.text)
            elif event.kind == "response":
                completed_response = event.text
                status = event.text.strip()
            elif event.kind == "thinking":
                status = event.text.strip()
            else:
                chunks.append(event.text)
                status = event.text.strip()
            if status:

                def _update_log(s: str) -> None:
                    DocGenerationLog.objects.filter(pk=log_pk).update(agent_output=s)

                await asyncio.get_running_loop().run_in_executor(None, _update_log, status)
        return completed_response or "".join(chunks)

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_generate())
    finally:
        loop.close()


def _scan_library_files(root_dir: Path) -> tuple[list[_LibraryFile], int]:
    """Return ([{path, size}, ...], total_size) for *.md files under root_dir.

    Paths are relative to root_dir and sorted; total_size is the sum of bytes.
    """
    files: list[_LibraryFile] = []
    total = 0
    if root_dir.exists() and root_dir.is_dir():
        for f in sorted(root_dir.rglob("*.md")):
            if f.is_file():
                size = f.stat().st_size
                files.append({"path": str(f.relative_to(root_dir)), "size": size})
                total += size
    return files, total


def _run_docgen_background(
    log_pk: str,
    prompt: str,
    user_id: int,
    enabled_tools: list[str],
    selected_db_names: list[str],
    selected_doc_names: list[str],
    destination: str,
    safe_name: str,
    selected_codebase_names: list[str] | None = None,
) -> None:
    """Run doc generation in a background thread. Updates DocGenerationLog when done."""
    import django

    django.setup()

    log_entry = DocGenerationLog.objects.get(pk=log_pk)
    t_start = time.monotonic()

    try:
        result = _execute_docgen(
            log_pk,
            prompt,
            user_id,
            enabled_tools,
            selected_db_names,
            selected_doc_names,
            f"docgen-{user_id}",
            _get_docgen_timeout(),
            selected_codebase_names=selected_codebase_names,
        )
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        log_entry.status = "failed"
        log_entry.error_message = str(e)
        log_entry.execution_time_ms = elapsed_ms
        log_entry.completed_at = timezone.now()
        log_entry.save()
        logger.exception("AI documentation generation failed (background)")
        return

    elapsed_ms = int((time.monotonic() - t_start) * 1000)

    get(DocSourceService).sync_from_filesystem()

    generated_file = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR) / destination / safe_name
    file_size = None
    warnings: list[str] = []

    if generated_file.exists():
        try:
            file_content = generated_file.read_text(encoding="utf-8", errors="replace")
            file_size = generated_file.stat().st_size
            if "(Database unavailable — skipped)" in file_content:
                warnings.append("Some databases were unavailable during generation.")
        except OSError:
            pass

    parsed_errors = _parse_docgen_result(result)

    if parsed_errors or warnings:
        status = "partial"
    else:
        status = "success"

    log_entry.status = status
    log_entry.execution_time_ms = elapsed_ms
    log_entry.completed_at = timezone.now()
    log_entry.file_size = file_size
    log_entry.errors = parsed_errors
    log_entry.agent_output = result
    log_entry.save()


def _run_docgen_library_background(
    log_pk: str,
    prompt: str,
    user_id: int,
    enabled_tools: list[str],
    selected_db_names: list[str],
    selected_doc_names: list[str],
    library_root: str,
    source_doc_type: str,
    selected_codebase_names: list[str] | None = None,
) -> None:
    """Run library generation in a background thread, then scan the folder tree.

    Unlike the single-file runner, completion is judged by what the agent wrote
    under the library root (any *.md files), not a single expected filename.
    """
    import django

    django.setup()

    log_entry = DocGenerationLog.objects.get(pk=log_pk)
    t_start = time.monotonic()

    try:
        result = _execute_docgen(
            log_pk,
            prompt,
            user_id,
            enabled_tools,
            selected_db_names,
            selected_doc_names,
            f"docgen-lib-{user_id}",
            _get_doclibgen_timeout(),
            selected_codebase_names=selected_codebase_names,
        )
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        log_entry.status = "failed"
        log_entry.error_message = str(e)
        log_entry.execution_time_ms = elapsed_ms
        log_entry.completed_at = timezone.now()
        log_entry.save()
        logger.exception("AI documentation library generation failed (background)")
        return

    elapsed_ms = int((time.monotonic() - t_start) * 1000)

    get(DocSourceService).sync_from_filesystem()

    # Apply the chosen documentation type to the newly registered source.
    # A library maps to its top-level folder under documentations/.
    top_folder = library_root.split("/")[0]
    DocumentationSource.objects.filter(folder_name=top_folder).update(doc_type=source_doc_type)

    root_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR) / library_root
    files, total_size = _scan_library_files(root_dir)

    warnings: list[str] = []
    for f in files:
        try:
            content = (root_dir / f["path"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "(Database unavailable — skipped)" in content:
            warnings.append("Some databases were unavailable during generation.")
            break

    parsed_errors = _parse_docgen_result(result)

    if not files:
        status = "failed"
        log_entry.error_message = (
            f"The agent finished but no documentation files were created under '{library_root}'."
        )
    elif parsed_errors or warnings:
        status = "partial"
    else:
        status = "success"

    log_entry.status = status
    log_entry.execution_time_ms = elapsed_ms
    log_entry.completed_at = timezone.now()
    log_entry.file_size = total_size
    log_entry.errors = parsed_errors
    log_entry.agent_output = result
    log_entry.save()


# ── Public entry points ──────────────────────────────────────────────────────


def _enabled_tools() -> list[str]:
    """Enabled tool names across active MCP servers, plus create_documentation."""
    enabled = list(
        ToolConfiguration.objects.filter(is_enabled=True, mcp_server__is_active=True).values_list(
            "tool_name", flat=True
        )
    )
    if "create_documentation" not in enabled:
        enabled.append("create_documentation")
    return enabled


def start_single(
    *,
    user: User,
    agent_config: AgentConfiguration,
    doc_name: str,
    doc_type: str,
    destination: str,
    scope: str,
    db_names: list[str],
    doc_names: list[str],
    codebase_names: list[str],
) -> DocGenerationLog:
    """Build the prompt, create the log, and start single-file generation."""
    base_prompt = build_doc_generation_prompt(doc_type, [], scope=scope)

    tool_instruction = (
        f"\n\nIMPORTANT: After generating the documentation content, you MUST save it "
        f"using the create_documentation tool with these parameters:\n"
        f'- destination: "{destination}"\n'
        f'- filename: "{doc_name}"\n'
    )
    if db_names:
        tool_instruction += f"- databases: {db_names} (to auto-append schema reference)\n"
    if doc_names:
        tool_instruction += (
            f"- reference_docs: {doc_names} "
            f"(the tool will append wiki-link references; use search_docs / "
            f"get_table_schema to read their content during generation)\n"
        )
        tool_instruction += (
            "\nWiki-link syntax: Use [[Source/path.md|Display Text]] to cross-reference "
            "other documentation pages. The viewer renders these as clickable links.\n"
        )
    if codebase_names:
        tool_instruction += (
            f"- codebases: {codebase_names} (explore them with list_codebases, "
            f"get_codebase_tree, read_codebase_file, and search_codebase to ground the docs "
            f"in the actual source code)\n"
        )
    tool_instruction += (
        "\nDo NOT output the documentation as a chat response. "
        "Use the create_documentation tool to write it directly."
    )

    prompt = base_prompt + tool_instruction

    safe_name = doc_name.replace("/", "").replace("\\", "").strip()
    if not safe_name.endswith(".md"):
        safe_name += ".md"

    log_entry = DocGenerationLog.objects.create(
        user=user,
        agent=agent_config,
        destination=destination,
        filename=safe_name,
        doc_type=doc_type,
        status="running",
        source_databases=db_names,
        source_docs=doc_names,
        prompt_used=prompt,
    )

    thread = threading.Thread(
        target=_run_docgen_background,
        args=(
            log_entry.pk,
            prompt,
            user.pk,
            _enabled_tools(),
            db_names,
            doc_names,
            destination,
            safe_name,
            codebase_names,
        ),
        daemon=True,
    )
    thread.start()
    return log_entry


def start_library(
    *,
    user: User,
    agent_config: AgentConfiguration,
    library_root: str,
    source_doc_type: str,
    db_names: list[str],
    doc_names: list[str],
    codebase_names: list[str],
) -> DocGenerationLog:
    """Build the prompt, create the log, and start multi-file library generation."""
    base_prompt = build_library_prompt(library_root, source_doc_type)

    is_database = source_doc_type == DocumentationSource.DocType.DATABASE.value
    overview_name = "Architecture.md" if is_database else "index.md"
    subfolder_hint = "Tables" if is_database else "Schemas"
    tool_instruction = (
        f"\n\nIMPORTANT — how to save the library:\n"
        f"- Write every file with the create_documentation tool, calling it once per file.\n"
        f'- Every file\'s `destination` MUST start with "{library_root}" '
        f'(use subfolders like "{library_root}/{subfolder_hint}" as needed).\n'
        f'- Create a "{library_root}/{overview_name}" overview that links to the other pages.\n'
    )
    if db_names:
        tool_instruction += (
            f"- For schema pages, pass databases={db_names} to "
            f"create_documentation so the schema reference is auto-appended.\n"
        )
    if doc_names:
        tool_instruction += (
            f"- Reference existing docs {doc_names} where relevant; read them "
            f"with search_docs / get_table_schema during generation.\n"
        )
    if codebase_names:
        tool_instruction += (
            f"- Ground pages in the codebases {codebase_names}; explore them with "
            f"list_codebases, get_codebase_tree, read_codebase_file, and search_codebase.\n"
        )
    tool_instruction += (
        "- Use wiki-link syntax [[Path/Page.md|Display Text]] to cross-link pages.\n"
        "- Do NOT output the documentation as a chat response. Write every file with "
        "the create_documentation tool."
    )

    prompt = base_prompt + tool_instruction

    log_entry = DocGenerationLog.objects.create(
        user=user,
        agent=agent_config,
        destination=library_root,
        filename="",
        doc_type="library",
        is_library=True,
        status="running",
        source_databases=db_names,
        source_docs=doc_names,
        prompt_used=prompt,
    )

    thread = threading.Thread(
        target=_run_docgen_library_background,
        args=(
            log_entry.pk,
            prompt,
            user.pk,
            _enabled_tools(),
            db_names,
            doc_names,
            library_root,
            source_doc_type,
            codebase_names,
        ),
        daemon=True,
    )
    thread.start()
    return log_entry


# ── Status polling ───────────────────────────────────────────────────────────


def _library_status_payload(log_entry: DocGenerationLog, data: dict[str, Any]) -> dict[str, Any]:
    """Status dict for a library generation run (folder-level tracking)."""
    root_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR) / log_entry.destination
    files, total_size = _scan_library_files(root_dir)

    if log_entry.status == "running":
        data["agent_output"] = log_entry.agent_output
        data["file_count"] = len(files)
        return data

    if log_entry.status == "failed":
        data["error"] = log_entry.error_message
        return data

    warnings: list[str] = []
    if log_entry.errors:
        for err in log_entry.errors:
            db_name = err.get("database", "unknown")
            warnings.append(f"Database '{db_name}' was unavailable.")

    data.update(
        {
            "folder": log_entry.destination,
            "file_count": len(files),
            "files": files,
            "total_size": total_size,
            "file_size": log_entry.file_size,
            "warnings": warnings,
        }
    )
    return data


def status_payload(log_entry: DocGenerationLog) -> dict[str, Any]:
    """Poll payload for a doc generation run. Mirrors the legacy status views."""
    data: dict[str, Any] = {
        "id": log_entry.pk,
        "status": log_entry.status,
        "execution_time_ms": log_entry.execution_time_ms,
        "is_library": log_entry.is_library,
    }

    if log_entry.is_library:
        return _library_status_payload(log_entry, data)

    if log_entry.status == "running":
        generated_file = (
            Path(settings.TETHERDUST_DOCUMENTATIONS_DIR)
            / log_entry.destination
            / log_entry.filename
        )
        data["file_exists"] = generated_file.exists()
        data["agent_output"] = log_entry.agent_output
        return data

    if log_entry.status == "failed":
        data["error"] = log_entry.error_message
        return data

    generated_file = (
        Path(settings.TETHERDUST_DOCUMENTATIONS_DIR) / log_entry.destination / log_entry.filename
    )
    preview = ""
    if generated_file.exists():
        try:
            lines = generated_file.read_text(encoding="utf-8", errors="replace").splitlines()
            preview = "\n".join(lines[:10])
            if len(lines) > 10:
                preview += "\n\n*... (truncated)*"
        except OSError:
            pass

    warnings: list[str] = []
    if log_entry.errors:
        for err in log_entry.errors:
            db_name = err.get("database", "unknown")
            warnings.append(f"Database '{db_name}' was unavailable.")

    data.update(
        {
            "folder": log_entry.destination,
            "file_count": 1,
            "content": preview,
            "file_size": log_entry.file_size,
            "warnings": warnings,
        }
    )
    return data
