"""Prefixed string primary-key generation.

Every model owns a short ``__prefix__`` and a matching ``generate_<prefix>_id``
default. IDs look like ``agt_3f9c…`` — a human-readable type tag plus 32 hex
characters of CSPRNG entropy (128 bits), comfortably within ``CharField(64)``.

The generator is dependency-free. If time-ordered IDs are ever wanted, swap the
``secrets.token_hex(16)`` body for a ULID without touching any call site.
"""

import secrets

_ENTROPY_BYTES = 16  # 128 bits -> 32 hex chars


def generate_id(prefix: str) -> str:
    """Return a new prefixed identifier, e.g. ``agt_<32 hex>``."""
    return f"{prefix}_{secrets.token_hex(_ENTROPY_BYTES)}"


def generate_agt_id() -> str:
    return generate_id("agt")


def generate_dgl_id() -> str:
    return generate_id("dgl")


def generate_rol_id() -> str:
    return generate_id("rol")


def generate_usp_id() -> str:
    return generate_id("usp")


def generate_ses_id() -> str:
    return generate_id("ses")


def generate_msg_id() -> str:
    return generate_id("msg")


def generate_db_id() -> str:
    return generate_id("db")


def generate_cb_id() -> str:
    return generate_id("cb")


def generate_doc_id() -> str:
    return generate_id("doc")


def generate_mcp_id() -> str:
    return generate_id("mcp")


def generate_tool_id() -> str:
    return generate_id("tool")


def generate_prm_id() -> str:
    return generate_id("prm")


def generate_cfg_id() -> str:
    return generate_id("cfg")


def generate_qal_id() -> str:
    return generate_id("qal")


def generate_dsh_id() -> str:
    return generate_id("dsh")


def generate_cht_id() -> str:
    return generate_id("cht")


def generate_cgl_id() -> str:
    return generate_id("cgl")


def generate_rpt_id() -> str:
    return generate_id("rpt")


def generate_rex_id() -> str:
    return generate_id("rex")


def generate_tth_id() -> str:
    return generate_id("tth")


def generate_tvr_id() -> str:
    return generate_id("tvr")
