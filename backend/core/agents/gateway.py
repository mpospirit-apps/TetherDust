"""Shared-secret authentication for the agent CLI gateways.

The Codex/Claude FastAPI gateways (`/chat`, `/abort`, `/auth/*`,
`/update-agents-md`) sit on the internal Docker network with no user-facing
auth. When ``AGENT_GATEWAY_SECRET`` is set, every Django→gateway call carries a
matching ``X-Gateway-Secret`` header and the gateway rejects requests without
it — so a process that can reach the gateway over the network cannot drive the
agent (with attacker-chosen credentials/permissions) or read stored tokens.

Empty when unset, which disables enforcement on both sides for local/dev use.
The shipped docker-compose sets the secret.
"""

from __future__ import annotations

import os


def gateway_auth_headers() -> dict[str, str]:
    """Return the gateway shared-secret header, or {} when unconfigured."""
    secret = os.getenv("AGENT_GATEWAY_SECRET", "")
    return {"X-Gateway-Secret": secret} if secret else {}
