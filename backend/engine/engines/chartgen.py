"""AI dashboard/chart generation orchestration.

Ported out of the legacy ``management/views/dashboard.py`` so the API layer drives
generation without the to-be-deleted view module. The agent runs in a background
thread (using the *active* agent), creating a dashboard + charts via the
``create_dashboard`` / ``add_chart`` MCP tools, and streaming status into a
``ChartGenerationLog`` the SPA polls via ``status_payload``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any

from django.contrib.auth.models import User
from django.utils import timezone

from engine.models import (
    AgentConfiguration,
    Chart,
    ChartGenerationLog,
    Dashboard,
    ToolConfiguration,
)
from engine.prompts import DASHBOARD_TEMPLATES
from engine.services import SystemConfigService, get

logger = logging.getLogger(__name__)


def _get_chartgen_timeout() -> float:
    val = get(SystemConfigService).get_value("chartgen_timeout", None)
    if val is not None:
        return float(val)
    return float(os.getenv("CHARTGEN_TIMEOUT", "1800"))


def _enabled_tools() -> list[str]:
    enabled = list(
        ToolConfiguration.objects.filter(is_enabled=True, mcp_server__is_active=True).values_list(
            "tool_name", flat=True
        )
    )
    for tool_name in ("create_dashboard", "add_chart"):
        if tool_name not in enabled:
            enabled.append(tool_name)
    return enabled


def _run_background(
    log_pk: str,
    prompt: str,
    user_id: int,
    enabled_tools: list[str],
    selected_db_names: list[str],
    selected_doc_names: list[str],
    dashboard_name: str,
    selected_codebase_names: list[str] | None = None,
) -> None:
    """Run dashboard generation in a background thread; update the log when done."""
    import django

    django.setup()

    from engine.agents import get_agent
    from engine.agents.stream import parse_chunk, tool_status_label

    log_entry = ChartGenerationLog.objects.get(pk=log_pk)
    t_start = time.monotonic()

    try:
        agent = get_agent()
        chartgen_timeout = _get_chartgen_timeout()

        async def _generate() -> str:
            chunks = []
            completed_response = ""
            async for chunk in agent.chat(
                message=prompt,
                user_id=user_id,
                session_id=f"chartgen-{user_id}",
                allowed_tools=enabled_tools or None,
                allowed_databases=selected_db_names,
                allowed_doc_sources=selected_doc_names,
                allowed_codebases=selected_codebase_names,
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

                    def _update_log(s: str) -> None:
                        ChartGenerationLog.objects.filter(pk=log_pk).update(agent_output=s)

                    await asyncio.get_running_loop().run_in_executor(None, _update_log, status)
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
        log_entry.completed_at = timezone.now()
        log_entry.save()
        logger.exception("AI dashboard generation failed (background)")
        return

    elapsed_ms = int((time.monotonic() - t_start) * 1000)

    dashboard = Dashboard.objects.filter(name=dashboard_name).first()
    charts_created = 0
    if dashboard:
        charts_created = Chart.objects.filter(dashboard=dashboard).count()
        dashboard.created_by_id = user_id
        dashboard.save(update_fields=["created_by_id"])

    if charts_created == 0:
        status = "failed"
        log_entry.error_message = log_entry.error_message or "No charts were created by the agent."
    else:
        status = "success"

    log_entry.status = status
    log_entry.execution_time_ms = elapsed_ms
    log_entry.completed_at = timezone.now()
    log_entry.charts_created = charts_created
    log_entry.agent_output = result
    log_entry.save()


def start_generation(
    *,
    user: User,
    agent_config: AgentConfiguration,
    dashboard_name: str,
    dashboard_type: str,
    prompt_override: str,
    db_names: list[str],
    doc_names: list[str],
    codebase_names: list[str],
) -> ChartGenerationLog:
    """Build the prompt, create the log, and start dashboard generation."""
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
    if db_names:
        tool_instruction += f"Available databases: {db_names}\n"
    if doc_names:
        tool_instruction += (
            f"Available documentation sources: {doc_names}\n"
            f"Use search_docs and get_table_schema to understand the data before writing queries.\n"
        )
    if codebase_names:
        tool_instruction += (
            f"Available codebases: {codebase_names}\n"
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
        user=user,
        agent=agent_config,
        dashboard_name=dashboard_name,
        status="running",
        source_databases=db_names,
        source_docs=doc_names,
        prompt_used=prompt,
    )

    thread = threading.Thread(
        target=_run_background,
        args=(
            log_entry.pk,
            prompt,
            user.pk,
            _enabled_tools(),
            db_names,
            doc_names,
            dashboard_name,
            codebase_names,
        ),
        daemon=True,
    )
    thread.start()
    return log_entry


def status_payload(log_entry: ChartGenerationLog) -> dict[str, Any]:
    """Poll payload for a dashboard-generation run. Mirrors the legacy status view."""
    data: dict[str, Any] = {
        "id": log_entry.pk,
        "status": log_entry.status,
        "execution_time_ms": log_entry.execution_time_ms,
    }

    if log_entry.status == "running":
        dashboard = Dashboard.objects.filter(name=log_entry.dashboard_name).first()
        if dashboard:
            data["dashboard_id"] = dashboard.pk
            data["charts_created"] = Chart.objects.filter(dashboard=dashboard).count()
        data["agent_output"] = log_entry.agent_output
        return data

    if log_entry.status == "failed":
        data["error"] = log_entry.error_message
        return data

    dashboard = Dashboard.objects.filter(name=log_entry.dashboard_name).first()
    data.update(
        {
            "dashboard_id": dashboard.pk if dashboard else None,
            "charts_created": log_entry.charts_created or 0,
            "dashboard_name": log_entry.dashboard_name,
        }
    )
    return data
