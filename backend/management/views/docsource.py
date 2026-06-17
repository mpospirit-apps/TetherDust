"""Documentation source CRUD + AI generation background tasks."""

from pathlib import Path
from typing import Any, TypedDict

from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from engine.agents.stream import parse_chunk, tool_status_label
from engine.models import (
    AgentConfiguration,
    Codebase,
    DatabaseConnection,
    DocGenerationLog,
    DocumentationSource,
    ToolConfiguration,
)
from engine.prompts import build_doc_generation_prompt, build_library_prompt
from engine.services import DocSourceService, get

from management.views._helpers import staff_required

from ..forms import DocumentationSourceForm
from ._helpers import (
    _get_docgen_timeout,
    _get_doclibgen_timeout,
    _get_documentation_folder_choices,
    _parse_docgen_result,
    logger,
)


class _LibraryFile(TypedDict):
    path: str
    size: int


# Library generation is restricted to these two source categories (see the
# generate_library form). Used both for the form's Type dropdown and POST validation.
LIBRARY_DOC_TYPES = (
    DocumentationSource.DocType.DATABASE,
    DocumentationSource.DocType.CODEBASE,
)


@staff_required
def docsource_list_view(request: HttpRequest) -> HttpResponse:
    get(DocSourceService).sync_from_filesystem()
    sources = DocumentationSource.objects.all()

    return render(
        request,
        "management/docsources/list.html",
        {
            "sources": sources,
            "section": "docsources",
        },
    )


@staff_required
def docsource_add_picker_view(request: HttpRequest) -> HttpResponse:
    """Step 1 of Add Documentation: choose how to add a documentation source."""
    return render(
        request,
        "management/docsources/add_picker.html",
        {
            "section": "docsources",
        },
    )


@staff_required
def docsource_generate_page_view(request: HttpRequest) -> HttpResponse:
    """Standalone page for AI documentation generation."""
    docs_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR)
    dest_folders = []
    if docs_dir.exists() and docs_dir.is_dir():
        for dirpath in sorted(docs_dir.rglob("*")):
            if dirpath.is_dir() and not any(
                p.startswith(".") for p in dirpath.relative_to(docs_dir).parts
            ):
                dest_folders.append(str(dirpath.relative_to(docs_dir)))

    return render(
        request,
        "management/docsources/generate.html",
        {
            "section": "docsources",
            "databases": DatabaseConnection.objects.filter(is_active=True),
            "doc_sources": DocumentationSource.objects.filter(is_active=True),
            "codebases": Codebase.objects.filter(is_active=True),
            "agents": AgentConfiguration.objects.all(),
            "dest_folders": dest_folders,
        },
    )


@staff_required
def docsource_library_page_view(request: HttpRequest) -> HttpResponse:
    """Standalone page for AI documentation *library* generation (a folder tree)."""
    docs_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR)
    existing_folders = []
    if docs_dir.exists() and docs_dir.is_dir():
        for entry in sorted(docs_dir.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                existing_folders.append(entry.name)

    return render(
        request,
        "management/docsources/generate_library.html",
        {
            "section": "docsources",
            "databases": DatabaseConnection.objects.filter(is_active=True),
            "doc_sources": DocumentationSource.objects.filter(is_active=True),
            "codebases": Codebase.objects.filter(is_active=True),
            "agents": AgentConfiguration.objects.all(),
            "doc_type_choices": [
                c for c in DocumentationSource.DocType.choices if c[0] in LIBRARY_DOC_TYPES
            ],
            "existing_folders": existing_folders,
        },
    )


@staff_required
def docsource_form_view(request: HttpRequest, pk: str | None = None) -> HttpResponse:
    instance = get_object_or_404(DocumentationSource, pk=pk) if pk else None

    folder_choices = _get_documentation_folder_choices()
    if request.method == "POST":
        form = DocumentationSourceForm(
            request.POST, instance=instance, folder_choices=folder_choices
        )
        if form.is_valid():
            form.save()
            return redirect("management:docsource_list")
    else:
        form = DocumentationSourceForm(instance=instance, folder_choices=folder_choices)

    from engine.models import DOC_TYPE_DESCRIPTIONS

    return render(
        request,
        "management/docsources/form.html",
        {
            "form": form,
            "instance": instance,
            "section": "docsources",
            "doc_type_descriptions": DOC_TYPE_DESCRIPTIONS,
        },
    )


@staff_required
@require_POST
def docsource_delete_view(request: HttpRequest, pk: str) -> HttpResponse:
    import shutil

    obj = get_object_or_404(DocumentationSource, pk=pk)

    # Delete the folder on disk too. Without this, docsource_list_view's
    # sync_from_filesystem() would rediscover the orphaned folder and recreate
    # the source with the default DATABASE type. Guard the path so we only ever
    # remove a directory that lives directly under the documentations dir.
    docs_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR).resolve()
    folder = Path(get(DocSourceService).resolved_path(obj)).resolve()
    if folder != docs_dir and docs_dir in folder.parents and folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)

    obj.delete()
    return redirect("management:docsource_list")


@staff_required
def docsource_validate_view(request: HttpRequest, pk: str) -> HttpResponse:
    """Validate a documentation source path and return HTMX fragment."""
    obj = get_object_or_404(DocumentationSource, pk=pk)
    path = Path(get(DocSourceService).resolved_path(obj))

    if not path.exists():
        return HttpResponse('<span class="badge badge-error">Folder not found</span>')
    if not path.is_dir():
        return HttpResponse('<span class="badge badge-error">Not a directory</span>')

    patterns = obj.file_patterns if obj.file_patterns else ["*.md"]
    all_files = [f for p in patterns for f in path.rglob(p) if f.is_file()]
    file_count = len(all_files)

    if file_count == 0:
        return HttpResponse('<span class="badge badge-warning">No matching files</span>')

    import datetime

    latest_mtime = 0.0
    for f in all_files:
        mtime = f.stat().st_mtime
        if mtime > latest_mtime:
            latest_mtime = mtime

    last_mod = (
        datetime.datetime.fromtimestamp(latest_mtime).strftime("%b %d, %H:%M")
        if latest_mtime
        else "—"
    )
    return HttpResponse(
        f'<span class="badge badge-success">{file_count} files</span> '
        f'<span class="text-sec text-sm">Last modified: {last_mod}</span>'
    )


def _execute_docgen(
    log_pk: int,
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
    import asyncio

    from engine.agents import get_agent
    from engine.models import DocGenerationLog as _DocGenLog

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
                    _DocGenLog.objects.filter(pk=log_pk).update(agent_output=s)

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
    log_pk: int,
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
    import time

    import django

    django.setup()

    from django.conf import settings as bg_settings
    from django.utils import timezone as bg_tz
    from engine.models import DocGenerationLog as _DocGenLog

    log_entry = _DocGenLog.objects.get(pk=log_pk)
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
        log_entry.completed_at = bg_tz.now()
        log_entry.save()
        logger.exception("AI documentation generation failed (background)")
        return

    elapsed_ms = int((time.monotonic() - t_start) * 1000)

    get(DocSourceService).sync_from_filesystem()

    generated_file = Path(bg_settings.TETHERDUST_DOCUMENTATIONS_DIR) / destination / safe_name
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
    log_entry.completed_at = bg_tz.now()
    log_entry.file_size = file_size
    log_entry.errors = parsed_errors
    log_entry.agent_output = result
    log_entry.save()


def _run_docgen_library_background(
    log_pk: int,
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
    import time

    import django

    django.setup()

    from django.conf import settings as bg_settings
    from django.utils import timezone as bg_tz
    from engine.models import DocGenerationLog as _DocGenLog
    from engine.models import DocumentationSource as _DocSource

    log_entry = _DocGenLog.objects.get(pk=log_pk)
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
        log_entry.completed_at = bg_tz.now()
        log_entry.save()
        logger.exception("AI documentation library generation failed (background)")
        return

    elapsed_ms = int((time.monotonic() - t_start) * 1000)

    get(DocSourceService).sync_from_filesystem()

    # Apply the chosen documentation type to the newly registered source.
    # A library maps to its top-level folder under documentations/.
    top_folder = library_root.split("/")[0]
    _DocSource.objects.filter(folder_name=top_folder).update(doc_type=source_doc_type)

    root_dir = Path(bg_settings.TETHERDUST_DOCUMENTATIONS_DIR) / library_root
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
    log_entry.completed_at = bg_tz.now()
    log_entry.file_size = total_size
    log_entry.errors = parsed_errors
    log_entry.agent_output = result
    log_entry.save()


@staff_required
@require_POST
def docsource_generate_view(request: HttpRequest) -> HttpResponse:
    """Start documentation generation in a background thread.

    Returns immediately with a log_id that the frontend polls for status.
    """
    import threading

    if not isinstance(request.user, User):
        return JsonResponse({"error": "Forbidden"}, status=403)

    doc_name = request.POST.get("doc_name", "").strip()
    doc_type = request.POST.get("doc_type")
    db_ids = request.POST.getlist("source_db")
    doc_ids = request.POST.getlist("source_doc")
    codebase_ids = request.POST.getlist("source_codebase")
    agent_id = request.POST.get("agent")
    destination = request.POST.get("destination", "").strip()
    scope = request.POST.get("scope", "").strip()

    if not all([doc_name, doc_type, agent_id, destination]):
        return JsonResponse({"success": False, "error": "Missing required fields."})
    assert doc_type is not None

    destination = destination.replace("\\", "/")
    destination = "/".join(part for part in destination.split("/") if part and part != "..")
    if not destination:
        return JsonResponse({"success": False, "error": "Invalid destination folder name."})

    agent_config = get_object_or_404(AgentConfiguration, pk=agent_id)

    selected_db_names = [
        db.name for db in DatabaseConnection.objects.filter(pk__in=db_ids, is_active=True)
    ]
    selected_doc_names = [
        doc.folder_name
        for doc in DocumentationSource.objects.filter(pk__in=doc_ids, is_active=True)
    ]
    selected_codebase_names = [
        cb.name for cb in Codebase.objects.filter(pk__in=codebase_ids, is_active=True)
    ]

    base_prompt = build_doc_generation_prompt(doc_type, [], scope=scope)

    tool_instruction = (
        f"\n\nIMPORTANT: After generating the documentation content, you MUST save it "
        f"using the create_documentation tool with these parameters:\n"
        f'- destination: "{destination}"\n'
        f'- filename: "{doc_name}"\n'
    )
    if selected_db_names:
        tool_instruction += f"- databases: {selected_db_names} (to auto-append schema reference)\n"
    if selected_doc_names:
        tool_instruction += (
            f"- reference_docs: {selected_doc_names} "
            f"(the tool will append wiki-link references; use search_docs / "
            f"get_table_schema to read their content during generation)\n"
        )
        tool_instruction += (
            "\nWiki-link syntax: Use [[Source/path.md|Display Text]] to cross-reference "
            "other documentation pages. The viewer renders these as clickable links.\n"
        )
    if selected_codebase_names:
        tool_instruction += (
            f"- codebases: {selected_codebase_names} (explore them with list_codebases, "
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
        user=request.user,
        agent=agent_config,
        destination=destination,
        filename=safe_name,
        doc_type=doc_type,
        status="running",
        source_databases=selected_db_names,
        source_docs=selected_doc_names,
        prompt_used=prompt,
    )

    enabled_tools = list(
        ToolConfiguration.objects.filter(is_enabled=True, mcp_server__is_active=True).values_list(
            "tool_name", flat=True
        )
    )
    if "create_documentation" not in enabled_tools:
        enabled_tools.append("create_documentation")

    thread = threading.Thread(
        target=_run_docgen_background,
        args=(
            log_entry.pk,
            prompt,
            request.user.pk,
            enabled_tools,
            selected_db_names,
            selected_doc_names,
            destination,
            safe_name,
            selected_codebase_names,
        ),
        daemon=True,
    )
    thread.start()

    return JsonResponse(
        {
            "success": True,
            "log_id": log_entry.pk,
        }
    )


@staff_required
@require_POST
def docsource_generate_library_view(request: HttpRequest) -> HttpResponse:
    """Start AI documentation *library* generation in a background thread.

    The agent plans a folder tree and writes many files via repeated
    create_documentation calls. Returns a log_id the frontend polls for status.
    """
    import threading

    if not isinstance(request.user, User):
        return JsonResponse({"error": "Forbidden"}, status=403)

    library_name = request.POST.get("library_name", "").strip()
    source_doc_type = request.POST.get("source_doc_type", DocumentationSource.DocType.DATABASE)
    if source_doc_type not in LIBRARY_DOC_TYPES:
        source_doc_type = DocumentationSource.DocType.DATABASE
    db_ids = request.POST.getlist("source_db")
    doc_ids = request.POST.getlist("source_doc")
    codebase_ids = request.POST.getlist("source_codebase")
    agent_id = request.POST.get("agent")

    if not all([library_name, agent_id]):
        return JsonResponse({"success": False, "error": "Missing required fields."})

    # Reuse the destination sanitization used for single files; the library root
    # is a folder path inside documentations/.
    library_root = library_name.replace("\\", "/")
    library_root = "/".join(part for part in library_root.split("/") if part and part != "..")
    if not library_root:
        return JsonResponse({"success": False, "error": "Invalid library name."})

    agent_config = get_object_or_404(AgentConfiguration, pk=agent_id)

    selected_db_names = [
        db.name for db in DatabaseConnection.objects.filter(pk__in=db_ids, is_active=True)
    ]
    selected_doc_names = [
        doc.folder_name
        for doc in DocumentationSource.objects.filter(pk__in=doc_ids, is_active=True)
    ]
    selected_codebase_names = [
        cb.name for cb in Codebase.objects.filter(pk__in=codebase_ids, is_active=True)
    ]

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
    if selected_db_names:
        tool_instruction += (
            f"- For schema pages, pass databases={selected_db_names} to "
            f"create_documentation so the schema reference is auto-appended.\n"
        )
    if selected_doc_names:
        tool_instruction += (
            f"- Reference existing docs {selected_doc_names} where relevant; read them "
            f"with search_docs / get_table_schema during generation.\n"
        )
    if selected_codebase_names:
        tool_instruction += (
            f"- Ground pages in the codebases {selected_codebase_names}; explore them with "
            f"list_codebases, get_codebase_tree, read_codebase_file, and search_codebase.\n"
        )
    tool_instruction += (
        "- Use wiki-link syntax [[Path/Page.md|Display Text]] to cross-link pages.\n"
        "- Do NOT output the documentation as a chat response. Write every file with "
        "the create_documentation tool."
    )

    prompt = base_prompt + tool_instruction

    log_entry = DocGenerationLog.objects.create(
        user=request.user,
        agent=agent_config,
        destination=library_root,
        filename="",
        doc_type="library",
        is_library=True,
        status="running",
        source_databases=selected_db_names,
        source_docs=selected_doc_names,
        prompt_used=prompt,
    )

    enabled_tools = list(
        ToolConfiguration.objects.filter(is_enabled=True, mcp_server__is_active=True).values_list(
            "tool_name", flat=True
        )
    )
    if "create_documentation" not in enabled_tools:
        enabled_tools.append("create_documentation")

    thread = threading.Thread(
        target=_run_docgen_library_background,
        args=(
            log_entry.pk,
            prompt,
            request.user.pk,
            enabled_tools,
            selected_db_names,
            selected_doc_names,
            library_root,
            source_doc_type,
            selected_codebase_names,
        ),
        daemon=True,
    )
    thread.start()

    return JsonResponse(
        {
            "success": True,
            "log_id": log_entry.pk,
        }
    )


def _library_status_response(log_entry: DocGenerationLog, data: dict[str, Any]) -> JsonResponse:
    """Build the status JSON for a library generation run (folder-level tracking)."""
    root_dir = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR) / log_entry.destination
    files, total_size = _scan_library_files(root_dir)

    if log_entry.status == "running":
        data["agent_output"] = log_entry.agent_output
        data["file_count"] = len(files)
        return JsonResponse(data)

    if log_entry.status == "failed":
        data["error"] = log_entry.error_message
        return JsonResponse(data)

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
    return JsonResponse(data)


@staff_required
def docsource_generate_status_view(request: HttpRequest, pk: str) -> HttpResponse:
    """Poll endpoint for doc generation status. Returns current state of the log entry."""
    log_entry = get_object_or_404(DocGenerationLog, pk=pk)

    data: dict[str, Any] = {
        "status": log_entry.status,
        "execution_time_ms": log_entry.execution_time_ms,
        "is_library": log_entry.is_library,
    }

    if log_entry.is_library:
        return _library_status_response(log_entry, data)

    if log_entry.status == "running":
        generated_file = (
            Path(settings.TETHERDUST_DOCUMENTATIONS_DIR)
            / log_entry.destination
            / log_entry.filename
        )
        data["file_exists"] = generated_file.exists()
        data["agent_output"] = log_entry.agent_output
        return JsonResponse(data)

    if log_entry.status == "failed":
        data["error"] = log_entry.error_message
        return JsonResponse(data)

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
    return JsonResponse(data)
