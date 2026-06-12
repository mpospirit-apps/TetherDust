"""Dashboard + chart CRUD, AI chart generation, and chart data API."""

import json

from core.agents.stream import parse_chunk, tool_status_label
from core.engines.db_runner import run_query
from core.models import (
    AgentConfiguration,
    Chart,
    ChartGenerationLog,
    Codebase,
    Dashboard,
    DatabaseConnection,
    DocumentationSource,
    ToolConfiguration,
)
from core.prompts import DASHBOARD_TEMPLATES
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from sqlalchemy.exc import SQLAlchemyError

from ..forms import ChartForm, DashboardForm
from ._helpers import _get_chartgen_timeout, _serialize_sql_value, logger


@staff_member_required(login_url="/login/")
def dashboard_list_view_admin(request: HttpRequest) -> HttpResponse:
    dashboards = Dashboard.objects.annotate(chart_count=Count("charts")).all()
    return render(
        request,
        "console/dashboards/list.html",
        {
            "dashboards": dashboards,
            "section": "dashboards",
        },
    )


@staff_member_required(login_url="/login/")
def dashboard_form_view_admin(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    instance = get_object_or_404(Dashboard, pk=pk) if pk else None

    if request.method == "POST":
        form = DashboardForm(request.POST, instance=instance)
        if form.is_valid():
            dashboard = form.save(commit=False)
            if not instance:
                dashboard.created_by = request.user
            dashboard.save()
            form.save_m2m()
            return redirect("console:dashboard_list")
    else:
        form = DashboardForm(instance=instance)

    return render(
        request,
        "console/dashboards/form.html",
        {
            "form": form,
            "instance": instance,
            "section": "dashboards",
        },
    )


@staff_member_required(login_url="/login/")
@require_POST
def dashboard_delete_view_admin(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Dashboard, pk=pk)
    obj.delete()
    return redirect("console:dashboard_list")


@staff_member_required(login_url="/login/")
def dashboard_detail_view_admin(request: HttpRequest, pk: int) -> HttpResponse:
    dashboard = get_object_or_404(Dashboard, pk=pk)
    charts = dashboard.charts.filter(is_active=True).select_related("database")
    return render(
        request,
        "console/dashboards/detail.html",
        {
            "dashboard": dashboard,
            "charts": charts,
            "section": "dashboards",
        },
    )


@staff_member_required(login_url="/login/")
def chart_form_view(request: HttpRequest, dashboard_pk: int, pk: int | None = None) -> HttpResponse:
    dashboard = get_object_or_404(Dashboard, pk=dashboard_pk)
    instance = get_object_or_404(Chart, pk=pk, dashboard=dashboard) if pk else None

    if request.method == "POST":
        form = ChartForm(request.POST, instance=instance)
        if form.is_valid():
            chart = form.save(commit=False)
            chart.dashboard = dashboard
            chart.chart_type = "custom"
            chart.save()
            return redirect("console:dashboard_detail", pk=dashboard.pk)
    else:
        form = ChartForm(instance=instance)

    # Raw object for the client; rendered via {{ ...|json_script }} so arbitrary
    # query-result values (incl. a literal </script>) can't break out of the tag.
    cached_data = None
    if instance and isinstance(instance.cached_data, dict):
        rows = instance.cached_data.get("rows")
        if rows:
            cached_data = {
                "columns": instance.cached_data.get("columns", []),
                "data": rows,
                "refreshed_at": instance.cached_data.get("refreshed_at"),
            }

    active_agent = AgentConfiguration.get_active()
    active_agent_name = active_agent.name if active_agent else "agent"

    return render(
        request,
        "console/dashboards/chart_form.html",
        {
            "form": form,
            "instance": instance,
            "dashboard": dashboard,
            "section": "dashboards",
            "cached_data": cached_data,
            "active_agent_name": active_agent_name,
        },
    )


@staff_member_required(login_url="/login/")
@require_POST
def chart_delete_view(request: HttpRequest, dashboard_pk: int, pk: int) -> HttpResponse:
    chart = get_object_or_404(Chart, pk=pk, dashboard__pk=dashboard_pk)
    dashboard_id = chart.dashboard_id
    chart.delete()
    return redirect("console:dashboard_detail", pk=dashboard_id)


# Dashboard-generation prompt templates moved to ``core.prompts.dashboards``
# (Phase 1 prompt consolidation), imported as ``DASHBOARD_TEMPLATES`` above.


@staff_member_required(login_url="/login/")
def dashboard_generate_page_view(request: HttpRequest) -> HttpResponse:
    """Page for AI dashboard generation."""
    return render(
        request,
        "console/dashboards/generate.html",
        {
            "section": "dashboards",
            "databases": DatabaseConnection.objects.filter(is_active=True),
            "doc_sources": DocumentationSource.objects.filter(is_active=True),
            "codebases": Codebase.objects.filter(is_active=True),
            "agents": AgentConfiguration.objects.all(),
        },
    )


def _run_dashboard_gen_background(
    log_pk: int,
    prompt: str,
    user_id: int,
    enabled_tools: list[str],
    selected_db_names: list[str],
    selected_doc_names: list[str],
    dashboard_name: str,
    selected_codebase_names: list[str] | None = None,
) -> None:
    """Run dashboard generation in a background thread. Updates ChartGenerationLog when done."""
    import asyncio
    import time

    import django

    django.setup()

    from core.agents import get_agent
    from core.models import ChartGenerationLog as _ChartGenLog
    from core.models import Dashboard as _Dashboard
    from django.utils import timezone as bg_tz

    log_entry = _ChartGenLog.objects.get(pk=log_pk)
    t_start = time.monotonic()

    try:
        agent = get_agent()
        chartgen_timeout = _get_chartgen_timeout()

        async def _generate():
            chunks = []
            completed_response = ""
            async for chunk in agent.chat(
                message=prompt,
                user_id=user_id,
                session_id=f"chartgen-{user_id}",
                allowed_tools=enabled_tools or None,
                allowed_databases=selected_db_names or None,
                allowed_doc_sources=selected_doc_names or None,
                allowed_codebases=selected_codebase_names or None,
                timeout=chartgen_timeout,
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
                    await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda s=status: _ChartGenLog.objects.filter(pk=log_pk).update(
                            agent_output=s
                        ),
                    )
            return completed_response or "".join(chunks)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_generate())
        finally:
            loop.close()
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        log_entry.status = "failed"
        log_entry.error_message = str(e)
        log_entry.execution_time_ms = elapsed_ms
        log_entry.completed_at = bg_tz.now()
        log_entry.save()
        logger.exception("AI dashboard generation failed (background)")
        return

    elapsed_ms = int((time.monotonic() - t_start) * 1000)

    dashboard = _Dashboard.objects.filter(name=dashboard_name).first()
    charts_created = 0
    if dashboard:
        charts_created = dashboard.charts.count()
        dashboard.created_by_id = user_id
        dashboard.save(update_fields=["created_by_id"])

    if charts_created == 0:
        status = "failed"
        log_entry.error_message = log_entry.error_message or "No charts were created by the agent."
    else:
        status = "success"

    log_entry.status = status
    log_entry.execution_time_ms = elapsed_ms
    log_entry.completed_at = bg_tz.now()
    log_entry.charts_created = charts_created
    log_entry.agent_output = result
    log_entry.save()


@staff_member_required(login_url="/login/")
@require_POST
def dashboard_generate_view(request: HttpRequest) -> HttpResponse:
    """Start dashboard generation in a background thread."""
    import threading

    dashboard_name = request.POST.get("dashboard_name", "").strip()
    dashboard_type = request.POST.get("dashboard_type", "overview")
    db_ids = request.POST.getlist("source_db")
    doc_ids = request.POST.getlist("source_doc")
    codebase_ids = request.POST.getlist("source_codebase")
    agent_id = request.POST.get("agent")
    prompt_override = request.POST.get("prompt_override", "")

    if not all([dashboard_name, agent_id]):
        return JsonResponse({"success": False, "error": "Missing required fields."})

    if Dashboard.objects.filter(name=dashboard_name).exists():
        return JsonResponse(
            {"success": False, "error": f"A dashboard named '{dashboard_name}' already exists."}
        )

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

    if prompt_override.strip():
        base_prompt = prompt_override.strip()
    else:
        base_prompt = DASHBOARD_TEMPLATES.get(dashboard_type, DASHBOARD_TEMPLATES["overview"])

    tool_instruction = (
        f"\n\nIMPORTANT: You MUST use the create_dashboard tool first to create "
        f'a dashboard named "{dashboard_name}", then use the add_chart tool '
        f"to add charts to it.\n\n"
        f"For each chart, provide:\n"
        f"- A descriptive title\n"
        f"- A SQL SELECT query that produces the chart data\n"
        f"- Raw d3.js code that renders the chart. The code receives three arguments:\n"
        f"  - data: array of row objects from the SQL query\n"
        f"  - container: DOM element to render into\n"
        f"  - d3: the d3 library\n"
        f"  Use d3.select(container) as the root. Set width from container.clientWidth "
        f"and height from container.clientHeight.\n"
        f"- The database name to run the query against\n"
        f"- width: grid column span (3=quarter, 4=third, 6=half, 8=two-thirds, 12=full)\n\n"
    )
    if selected_db_names:
        tool_instruction += f"Available databases: {selected_db_names}\n"
    if selected_doc_names:
        tool_instruction += (
            f"Available documentation sources: {selected_doc_names}\n"
            f"Use search_docs and get_table_schema to understand the data before writing queries.\n"
        )
    if selected_codebase_names:
        tool_instruction += (
            f"Available codebases: {selected_codebase_names}\n"
            f"Use list_codebases, get_codebase_tree, read_codebase_file, and search_codebase "
            f"to understand the code behind the data.\n"
        )
    tool_instruction += (
        "\nUse list_tables and get_table_schema to explore database structure. "
        "Use query_database to test queries before creating charts.\n"
        "Do NOT output the dashboard as a chat response. Use the tools to create it."
    )

    prompt = base_prompt + tool_instruction

    log_entry = ChartGenerationLog.objects.create(
        user=request.user,
        agent=agent_config,
        dashboard_name=dashboard_name,
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
    for tool_name in ("create_dashboard", "add_chart"):
        if tool_name not in enabled_tools:
            enabled_tools.append(tool_name)

    thread = threading.Thread(
        target=_run_dashboard_gen_background,
        args=(
            log_entry.pk,
            prompt,
            request.user.id,
            enabled_tools,
            selected_db_names,
            selected_doc_names,
            dashboard_name,
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


@staff_member_required(login_url="/login/")
def dashboard_generate_status_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Poll endpoint for dashboard generation status."""
    log_entry = get_object_or_404(ChartGenerationLog, pk=pk)

    data = {
        "status": log_entry.status,
        "execution_time_ms": log_entry.execution_time_ms,
    }

    if log_entry.status == "running":
        dashboard = Dashboard.objects.filter(name=log_entry.dashboard_name).first()
        if dashboard:
            data["dashboard_id"] = dashboard.pk
            data["charts_created"] = dashboard.charts.count()
        data["agent_output"] = log_entry.agent_output
        return JsonResponse(data)

    if log_entry.status == "failed":
        data["error"] = log_entry.error_message
        return JsonResponse(data)

    dashboard = Dashboard.objects.filter(name=log_entry.dashboard_name).first()
    data.update(
        {
            "dashboard_id": dashboard.pk if dashboard else None,
            "charts_created": log_entry.charts_created or 0,
            "dashboard_name": log_entry.dashboard_name,
        }
    )
    return JsonResponse(data)


@staff_member_required(login_url="/login/")
@require_POST
def chart_preview_view(request: HttpRequest, dashboard_pk: int) -> HttpResponse:
    """Execute an ad-hoc SQL query for the edit-page preview.

    Accepts unsaved form values: {database_id, sql_query}. Validates the
    query with report_engine.validate_sql (same as ChartForm.clean_sql_query),
    executes against the selected DatabaseConnection, and returns
    {columns, data}. Does NOT write cached_data back to any Chart row.
    """
    from core.engines.report_engine import validate_sql

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    database_id = payload.get("database_id")
    sql_query = (payload.get("sql_query") or "").strip()

    if not database_id:
        return JsonResponse({"error": "database_id is required."}, status=400)
    if not sql_query:
        return JsonResponse({"error": "sql_query is required."}, status=400)

    db_conn = get_object_or_404(DatabaseConnection, pk=database_id)

    validation_error = validate_sql(sql_query, engine=db_conn.engine)
    if validation_error:
        return JsonResponse({"error": validation_error}, status=400)

    try:
        columns, raw_rows = run_query(db_conn, sql_query)
        rows = [{col: _serialize_sql_value(v) for col, v in zip(columns, row)} for row in raw_rows]
    except SQLAlchemyError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"columns": columns, "data": rows})


@staff_member_required(login_url="/login/")
def chart_state_view(request: HttpRequest, dashboard_pk: int, pk: int) -> HttpResponse:
    """Return the current editable state of a chart as JSON.

    Used by the edit page to re-read chart fields after the AI agent
    writes to the DB via the update_chart MCP tool.
    """
    chart = get_object_or_404(Chart, pk=pk, dashboard_id=dashboard_pk)
    return JsonResponse(
        {
            "title": chart.title,
            "description": chart.description,
            "sql_query": chart.sql_query,
            "custom_d3_code": chart.custom_d3_code,
        }
    )


@staff_member_required(login_url="/login/")
def chart_data_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Return chart data as JSON. Uses cached data unless ?refresh=1 is set."""
    chart = get_object_or_404(Chart.objects.select_related("database"), pk=pk)
    force_refresh = request.GET.get("refresh") == "1"

    if not force_refresh and chart.cached_data and chart.cached_data.get("rows"):
        return JsonResponse(
            {
                "columns": chart.cached_data.get("columns", []),
                "data": chart.cached_data.get("rows", []),
                "cached": True,
                "refreshed_at": chart.cached_data.get("refreshed_at"),
            }
        )

    try:
        db_conn = chart.database
        columns, raw_rows = run_query(db_conn, chart.sql_query)
        rows = [{col: _serialize_sql_value(v) for col, v in zip(columns, row)} for row in raw_rows]

        now_str = timezone.now().isoformat()
        chart.cached_data = {
            "columns": columns,
            "rows": rows,
            "refreshed_at": now_str,
        }
        chart.last_refreshed_at = timezone.now()
        chart.last_error = ""
        chart.save(update_fields=["cached_data", "last_refreshed_at", "last_error"])

        return JsonResponse(
            {
                "columns": columns,
                "data": rows,
                "cached": False,
                "refreshed_at": now_str,
            }
        )
    except Exception as e:
        chart.last_error = str(e)
        chart.save(update_fields=["last_error"])
        return JsonResponse({"error": str(e)}, status=500)
