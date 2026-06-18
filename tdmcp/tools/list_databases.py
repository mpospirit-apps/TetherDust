"""Tool: list_databases — list configured database connections."""

from ._db_shared import get_allowed_databases, get_db_service


async def list_databases() -> str:
    """List all configured database connections with their descriptions. \
Use this to discover which databases are available before querying. \
Each database may contain different data domains."""
    db_service = get_db_service()
    databases = db_service.list_databases()

    allowed = get_allowed_databases()
    if allowed is not None:
        databases = [db for db in databases if db.name in allowed]

    if not databases:
        return (
            "No databases configured or accessible. "
            "Contact your administrator to add database connections via the admin console."
        )

    # Format output
    lines = ["# Configured Databases\n"]

    for db in databases:
        lines.append(f"## {db.name}")
        lines.append(f"**Engine:** {db.engine}")
        if db.description:
            lines.append(f"**Description:** {db.description}")
        if db.host:
            port_str = f":{db.port}" if db.port else ""
            lines.append(f"**Host:** {db.host}{port_str}")
        if db.database:
            lines.append(f"**Database:** {db.database}")
        lines.append("")

    return "\n".join(lines)
