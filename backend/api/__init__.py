"""Consolidated REST API for TetherDust (DRF).

Mounted at ``/api/``:

- ``/api/v1/`` — public + admin endpoints for the SPA (session-cookie auth)
- ``/api/internal/`` — service-to-service endpoints for the MCP server (token auth)

The existing ``engine`` (models/services), ``workspace`` and ``management``
(WebSocket consumers/routing) apps are reused; this app owns the whole HTTP API
surface so there is a single source of truth for the REST contract.
"""
