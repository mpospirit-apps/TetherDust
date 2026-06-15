"""Forms for database, documentation, MCP, tool, prompt, and system-settings configuration."""

import json
from typing import Any

from core.forms.base import _BaseForm
from core.models import (
    Codebase,
    DatabaseConnection,
    DocumentationSource,
    MCPServerConfiguration,
    PromptConfiguration,
    parse_owner_repo,
)
from django import forms


class DatabaseConnectionForm(_BaseForm):
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            attrs={"placeholder": "Enter password", "autocomplete": "new-password"}
        ),
        help_text="Encrypted at rest. Leave blank to keep existing.",
    )

    class Meta:
        model = DatabaseConnection
        fields = [
            "name",
            "description",
            "engine",
            "host",
            "port",
            "database",
            "username",
            "password",
            "connection_string",
            "extra_options",
            "read_only",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "connection_string": forms.Textarea(attrs={"rows": 2}),
            "extra_options": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Don't pre-fill password for existing records
            self.fields["password"].widget.attrs["placeholder"] = "••••••••  (leave blank to keep)"

    def save(self, commit: bool = True) -> object:
        instance = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            instance.password = password
        elif not self.instance.pk:
            instance._password = ""
        if commit:
            instance.save()
        return instance


class DocumentationSourceForm(_BaseForm):
    class Meta:
        model = DocumentationSource
        fields = ["folder_name", "doc_type", "description", "file_patterns", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "file_patterns": forms.Textarea(attrs={"rows": 2, "placeholder": '["*.md"]'}),
        }

    def __init__(
        self,
        *args: object,
        folder_choices: list[tuple[str, str]] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        if folder_choices is not None:
            self.fields["folder_name"] = forms.ChoiceField(
                choices=folder_choices,
                label="Documentation Folder",
                help_text="Select a folder from the documentations/ directory",
            )
            self.fields["folder_name"].widget.attrs.setdefault("class", "form-control")

    def clean_folder_name(self) -> str:
        """Validate that the selected folder exists."""
        from pathlib import Path

        from django.conf import settings

        folder_name = self.cleaned_data["folder_name"]
        path = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR) / folder_name

        if not path.exists() or not path.is_dir():
            raise forms.ValidationError(f"Folder does not exist: {folder_name}")

        return str(folder_name)

    def clean(self) -> dict[str, Any]:
        """Validate that the configured patterns match at least one file."""
        cleaned_data = super().clean() or {}
        folder_name = cleaned_data.get("folder_name")
        file_patterns = cleaned_data.get("file_patterns") or ["*.md"]

        if folder_name:
            from pathlib import Path

            from django.conf import settings

            path = Path(settings.TETHERDUST_DOCUMENTATIONS_DIR) / folder_name
            if path.exists() and path.is_dir():
                file_count = sum(len(list(path.rglob(p))) for p in file_patterns)
                if file_count == 0:
                    self.add_error(
                        "file_patterns",
                        f'No files matching {file_patterns} found in "{folder_name}".',
                    )

        return cleaned_data


class CodebaseForm(_BaseForm):
    access_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            attrs={"placeholder": "Enter GitHub token", "autocomplete": "new-password"}
        ),
        help_text="Encrypted at rest. Leave blank for public repositories. A read-only "
        "(contents: read) fine-grained PAT is sufficient.",
    )

    class Meta:
        model = Codebase
        fields = [
            "name",
            "description",
            "provider",
            "repo_url",
            "branch",
            "subpath",
            "include_globs",
            "exclude_globs",
            "access_token",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "include_globs": forms.Textarea(attrs={"rows": 2, "placeholder": '["src/**", "*.py"]'}),
            "exclude_globs": forms.Textarea(
                attrs={"rows": 2, "placeholder": '["node_modules/*", "*.lock"]'}
            ),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance._access_token:
            self.fields["access_token"].widget.attrs["placeholder"] = (
                "••••••••  (leave blank to keep)"
            )

    def clean_repo_url(self) -> str:
        repo_url = self.cleaned_data["repo_url"]
        try:
            parse_owner_repo(repo_url)
        except ValueError:
            raise forms.ValidationError(
                "Enter a GitHub repository URL like https://github.com/owner/repo"
            )
        return str(repo_url)

    def save(self, commit: bool = True) -> object:
        instance = super().save(commit=False)
        token = self.cleaned_data.get("access_token")
        if token:
            instance.access_token = token
        elif not self.instance.pk:
            instance._access_token = ""
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class MCPServerConfigurationForm(_BaseForm):
    auth_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Enter bearer token",
                "autocomplete": "new-password",
            }
        ),
        help_text="Sent as Authorization: Bearer <token>. Encrypted at rest. Leave blank to keep existing.",  # noqa: E501
    )
    transport = forms.ChoiceField(
        choices=[
            ("streamable-http", "Streamable HTTP"),
            ("sse", "SSE"),
        ],
        initial="streamable-http",
        help_text="Streamable HTTP is the current MCP standard; pick SSE only if the server requires it.",  # noqa: E501
    )
    command_env = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": '{"NOTION_API_KEY": "ntn_..."}',
                "style": "font-family: 'Space Mono', monospace; font-size: 13px;",
            }
        ),
        help_text="JSON object of environment variables passed to the subprocess. Encrypted at rest.",  # noqa: E501
    )

    field_order = [
        "name",
        "description",
        "url",
        "transport",
        "auth_token",
        "headers",
        "command",
        "args",
        "command_env",
        "is_active",
    ]

    class Meta:
        model = MCPServerConfiguration
        fields = [
            "name",
            "description",
            "url",
            "transport",
            "headers",
            "command",
            "args",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "headers": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": '{"X-API-Key": "..."}',
                    "style": "font-family: 'Space Mono', monospace; font-size: 13px;",
                }
            ),
            "args": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": '["-y", "@notionhq/notion-mcp-server"]',
                    "style": "font-family: 'Space Mono', monospace; font-size: 13px;",
                }
            ),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance._auth_token:
            self.fields["auth_token"].widget.attrs["placeholder"] = (
                "••••••••  (leave blank to keep)"
            )
        if self.instance and self.instance.pk and self.instance._command_env:
            self.fields["command_env"].widget.attrs["placeholder"] = (
                "••••••••  (leave blank to keep)"
            )
            try:
                self.fields["command_env"].initial = json.dumps(self.instance.command_env, indent=2)
            except Exception:
                pass

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        command = (cleaned.get("command") or "").strip()
        url = (cleaned.get("url") or "").strip()
        if command and url:
            raise forms.ValidationError(
                "A server cannot have both a Command (local subprocess) and a URL (remote HTTP). Set one or the other."  # noqa: E501
            )
        if not command and not url and not (self.instance and self.instance.is_builtin):
            raise forms.ValidationError(
                "Provide either a URL (remote HTTP) or a Command (local subprocess)."
            )
        env_raw = cleaned.get("command_env", "")
        if env_raw:
            try:
                parsed = json.loads(env_raw)
                if not isinstance(parsed, dict):
                    raise forms.ValidationError(
                        {"command_env": 'Must be a JSON object, e.g. {"KEY": "value"}.'}
                    )
            except json.JSONDecodeError:
                raise forms.ValidationError({"command_env": "Invalid JSON."})
        return cleaned

    def save(self, commit: bool = True) -> object:
        instance = super().save(commit=False)
        token = self.cleaned_data.get("auth_token")
        if token:
            instance.auth_token = token
        elif not self.instance.pk:
            instance._auth_token = ""
        env_raw = self.cleaned_data.get("command_env", "")
        if env_raw:
            instance.command_env = json.loads(env_raw)
        elif not self.instance.pk:
            instance._command_env = ""
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class PromptConfigurationForm(_BaseForm):
    class Meta:
        model = PromptConfiguration
        fields = [
            "prompt_name",
            "display_name",
            "is_enabled",
            "content",
        ]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "rows": 12,
                    "placeholder": "Analyze the given table. First get its schema, then query a sample of rows, and provide insights about the data types, patterns, and any potential issues.",  # noqa: E501
                }
            ),
        }


class SMTPSettingsForm(forms.Form):
    """Form for configuring SMTP email settings."""

    smtp_host = forms.CharField(
        max_length=255,
        required=False,
        label="SMTP Host",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "smtp.gmail.com"}),
    )
    smtp_port = forms.IntegerField(
        required=False,
        initial=587,
        label="SMTP Port",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    smtp_username = forms.CharField(
        max_length=255,
        required=False,
        label="Username",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "user@example.com"}),
    )
    smtp_password = forms.CharField(
        max_length=255,
        required=False,
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "new-password",
                "placeholder": "Enter SMTP password",
            }
        ),
    )
    smtp_use_tls = forms.BooleanField(
        required=False,
        initial=True,
        label="Use TLS",
        help_text="Enable TLS encryption (recommended for port 587)",
    )
    smtp_from_email = forms.EmailField(
        required=False,
        label="From Email Address",
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "noreply@example.com"}
        ),
    )
    email_max_rows = forms.IntegerField(
        required=False,
        initial=10000,
        label="Max Rows in CSV Attachment",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text="Maximum number of rows included in the CSV attached to report emails.",
        min_value=1,
    )


class GeneralSettingsForm(forms.Form):
    """Form for configuring general operational settings."""

    codex_service_url = forms.CharField(
        max_length=500,
        required=False,
        label="Codex Service URL",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "http://codex:8002"}),
        help_text="URL of the Codex API gateway service.",
    )
    mcp_base_url = forms.CharField(
        max_length=500,
        required=False,
        label="MCP Base URL",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "http://mcp:8001"}),
        help_text="Base URL of the MCP server.",
    )
    docgen_timeout = forms.IntegerField(
        required=False,
        initial=1800,
        label="Doc Gen Timeout (seconds)",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text="Maximum seconds to wait for AI single-file documentation generation.",
        min_value=1,
    )
    doclibgen_timeout = forms.IntegerField(
        required=False,
        initial=3600,
        label="Doc Library Gen Timeout (seconds)",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text="Maximum seconds to wait for AI documentation library (multi-file) generation.",
        min_value=1,
    )
    chartgen_timeout = forms.IntegerField(
        required=False,
        initial=1800,
        label="Chart Gen Timeout (seconds)",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text="Maximum seconds to wait for AI chart generation.",
        min_value=1,
    )
    max_row_limit = forms.IntegerField(
        required=False,
        label="Max Row Limit",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 1000"}),
        help_text="Maximum rows the agent may return per query. Leave blank for no limit.",
        min_value=1,
    )
    hot_reload_interval = forms.IntegerField(
        required=False,
        label="Hot Reload Interval (seconds)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 30"}),
        help_text="How often the MCP server reloads documentation. Leave blank to disable.",
        min_value=1,
    )
