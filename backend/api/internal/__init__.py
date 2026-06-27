"""Service-to-service internal API (mounted at /api/internal/).

These endpoints are called by the tdmcp MCP server to persist mutating tool
results (dashboards, charts, tether graphs) through the Django ORM instead of
writing to Postgres directly. They authenticate with a shared service token, not
the session cookie.
"""
