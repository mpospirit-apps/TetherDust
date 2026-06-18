"""Prompt for the AI chart-edit consumer.

Call site: ``management/consumers/chart_edit.py``. Injects the chart's current state
into every turn so the agent always sees what it is editing, then instructs it to
persist changes via the ``update_chart`` MCP tool.
"""

from typing import Any


def build_chart_edit_prompt(chart_info: dict[str, Any], user_message: str) -> str:
    return (
        f"[Chart context — current state, id={chart_info['chart_id']}]\n"
        f"title: {chart_info['title']}\n"
        f"description: {chart_info['description']}\n"
        f"database: {chart_info['database_name']}\n"
        f"sql_query:\n{chart_info['sql_query']}\n\n"
        f"custom_d3_code:\n{chart_info['custom_d3_code']}\n\n"
        "[Instructions]\n"
        "Modify this chart by calling the update_chart MCP tool with "
        f"chart_id={chart_info['chart_id']}. Only pass the fields you "
        "actually want to change (title, description, sql_query, d3_code). "
        "Preserve the strict theme-palette color rules for any d3 code "
        "you write. When you need to understand the data, call "
        "list_tables / get_table_schema / query_database first. "
        "After making the change, reply with a brief one-line summary "
        "of what you changed — nothing more.\n\n"
        "[User request]\n"
        f"{user_message}"
    )
