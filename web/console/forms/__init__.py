"""Forms for the TetherDust mission-control panel.

Forms are split across domain modules. This package re-exports every public
name so views can `from console.forms import X` (or `from ..forms import X`).
"""

from .agent import AgentConfigurationForm
from .auth import RoleForm, UserCreateForm, UserProfileForm
from .connections import (
    CodebaseForm,
    DatabaseConnectionForm,
    DocumentationSourceForm,
    GeneralSettingsForm,
    MCPServerConfigurationForm,
    PromptConfigurationForm,
    SMTPSettingsForm,
)
from .dashboards import ChartForm, DashboardForm
from .reports import ReportDefinitionForm
from .tethers import TetherForm

__all__ = [
    "AgentConfigurationForm",
    "RoleForm",
    "UserCreateForm",
    "UserProfileForm",
    "CodebaseForm",
    "DatabaseConnectionForm",
    "DocumentationSourceForm",
    "GeneralSettingsForm",
    "MCPServerConfigurationForm",
    "PromptConfigurationForm",
    "SMTPSettingsForm",
    "ChartForm",
    "DashboardForm",
    "ReportDefinitionForm",
    "TetherForm",
]
