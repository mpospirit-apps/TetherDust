"""TetherDust Django models.

All configuration is managed via Django Admin - no hardcoding required.

Models are split across domain modules. This package re-exports every public
name so callers can use `from core.models import X`.
"""

from ._encryption import decrypt_value, encrypt_value, get_fernet
from .agent import AgentConfiguration, DocGenerationLog
from .auth import Role, UserProfile
from .chat import ChatMessage, ChatSession
from .connections import (
    DOC_TYPE_DESCRIPTIONS,
    Codebase,
    DatabaseConnection,
    DocumentationSource,
    MCPServerConfiguration,
    PromptConfiguration,
    QueryAuditLog,
    SystemConfiguration,
    ToolConfiguration,
    parse_owner_repo,
)
from .dashboards import Chart, ChartGenerationLog, Dashboard
from .reports import ReportDefinition, ReportExecution
from .tethers import Tether, TetherVersion

__all__ = [
    # encryption helpers
    "decrypt_value",
    "encrypt_value",
    "get_fernet",
    # connections
    "DOC_TYPE_DESCRIPTIONS",
    "Codebase",
    "parse_owner_repo",
    "DatabaseConnection",
    "DocumentationSource",
    "MCPServerConfiguration",
    "PromptConfiguration",
    "QueryAuditLog",
    "SystemConfiguration",
    "ToolConfiguration",
    # auth
    "Role",
    "UserProfile",
    # agent
    "AgentConfiguration",
    "DocGenerationLog",
    # chat
    "ChatMessage",
    "ChatSession",
    # reports
    "ReportDefinition",
    "ReportExecution",
    # dashboards
    "Chart",
    "ChartGenerationLog",
    "Dashboard",
    # tethers
    "Tether",
    "TetherVersion",
]
