"""Service layer for the engine app.

Business logic that used to live on models is here, reached via the ``get``
registry: ``get(SomeService).method(...)``. Services are stateless singletons.
"""

from .agent import AgentService
from .connection import CodebaseService, ConnectionService, DocSourceService
from .mcp_server import McpServerService, ToolService
from .permissions import PermissionService
from .registry import get
from .report import ReportService
from .system_config import SystemConfigService
from .tether import TetherService

__all__ = [
    "get",
    "AgentService",
    "CodebaseService",
    "ConnectionService",
    "DocSourceService",
    "McpServerService",
    "ToolService",
    "PermissionService",
    "ReportService",
    "SystemConfigService",
    "TetherService",
]
