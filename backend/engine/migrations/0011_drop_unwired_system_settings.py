"""Drop SystemConfiguration keys that no code reads any more.

The settings panel exposed `codex_service_url`, `mcp_base_url`, `max_row_limit`
and `hot_reload_interval`, but nothing (or only part of the stack) honoured them:
gateway URLs now resolve per-agent → env var, the MCP base URL is env-only, row
caps come from the user's Role, and hot reload is a tdmcp-side env var.
"""

from __future__ import annotations

from django.db import migrations

DEAD_KEYS = [
    "codex_service_url",
    "codex_api_service_url",
    "claude_service_url",
    "claude_api_service_url",
    "mcp_base_url",
    "max_row_limit",
    "hot_reload_interval",
]


def drop_dead_keys(apps, schema_editor):
    SystemConfiguration = apps.get_model("engine", "SystemConfiguration")
    SystemConfiguration.objects.filter(key__in=DEAD_KEYS).delete()


class Migration(migrations.Migration):
    dependencies = [("engine", "0010_alter_agentconfiguration_options")]

    operations = [migrations.RunPython(drop_dead_keys, migrations.RunPython.noop)]
