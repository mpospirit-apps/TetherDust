"""Forms for agent configuration."""

from core.forms.base import _BaseForm
from core.models import AgentConfiguration
from django import forms


class AgentConfigurationForm(_BaseForm):
    field_order = ["name", "agent_type", "is_active", "service_url", "system_prompt"]

    # Non-model field: the provider API key for API-key agents (codex_api,
    # openai_api). Stored encrypted via AgentConfiguration.set_api_key() in the
    # view, not by the ModelForm. Leaving it blank on edit keeps the existing key.
    api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "placeholder": "sk-…",
                "autocomplete": "new-password",
            },
        ),
        help_text="Provider API key (e.g. OpenAI). Leave blank to keep the current key.",
    )

    # Non-model field: the Claude Code subscription OAuth token (auth-token
    # agents authenticated by a Claude Pro/Max account). Stored encrypted via
    # AgentConfiguration.set_auth_token() in the view. Blank on edit keeps the
    # existing token.
    oauth_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "placeholder": "sk-ant-oat…",
                "autocomplete": "new-password",
            },
        ),
        help_text="Claude Code OAuth token from `claude setup-token` (run it on a "
        "machine signed in to a Claude Pro/Max subscription). Leave blank to keep "
        "the current token.",
    )

    # Non-model fields persisted into AgentConfiguration.settings. Populated from
    # the instance's settings in __init__. `model` is shared between direct API
    # agents (where the provider names the model) and Codex agents (where it maps
    # to `codex exec -m`); leaving it blank keeps Codex's built-in default.
    model = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "gpt-4o"}),
        # Direct-API agents get per-preset model guidance rendered in the form
        # template (each provider names models differently); this text covers the
        # CLI agents, where the field maps to the CLI's own model flag.
        help_text="Model name as the backend expects it — for Codex, gpt-5.5 or "
        "gpt-5.3-codex; for Claude Code, sonnet, opus, or a full model id. Leave "
        "blank to use the default.",
    )
    # Codex-only: maps to `model_reasoning_effort`. Blank = Codex default.
    REASONING_EFFORT_CHOICES = [
        ("", "Default"),
        ("minimal", "Minimal"),
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("xhigh", "Extra high"),
    ]
    reasoning_effort = forms.ChoiceField(
        required=False,
        choices=REASONING_EFFORT_CHOICES,
        help_text="Reasoning depth for Codex agents. Higher effort improves "
        "complex reasoning at the cost of latency. Availability depends on the "
        "selected model and subscription tier.",
    )
    base_url = forms.CharField(
        required=False,
        widget=forms.URLInput(attrs={"placeholder": "https://api.openai.com/v1"}),
        help_text="OpenAI-compatible API base URL (no trailing /chat/completions).",
    )

    class Meta:
        model = AgentConfiguration
        fields = ["name", "agent_type", "is_active", "service_url", "system_prompt"]
        widgets = {
            "system_prompt": forms.Textarea(
                attrs={
                    "rows": 20,
                    "style": "font-family: 'Space Mono', monospace; font-size: 13px;",
                }
            ),
            "service_url": forms.URLInput(
                attrs={
                    "placeholder": "http://codex:8002",
                }
            ),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        # Populate from saved settings only when present, so a per-type default
        # passed via `initial` (e.g. the Ollama base_url for a new agent) is not
        # clobbered by an empty string.
        settings = getattr(self.instance, "settings", None) or {}
        if isinstance(settings, dict):
            if settings.get("model"):
                self.fields["model"].initial = settings["model"]
            if settings.get("reasoning_effort"):
                self.fields["reasoning_effort"].initial = settings["reasoning_effort"]
            if settings.get("base_url"):
                self.fields["base_url"].initial = settings["base_url"]

    def clean(self) -> dict[str, object]:
        cleaned = super().clean()
        agent_type = cleaned.get("agent_type") or (
            self.instance.agent_type if self.instance and self.instance.pk else None
        )
        # API-key agents require a key on creation. On edit, blank means "keep
        # existing", so only require it when no key is stored yet.
        api_key_types = {"codex_api", "claude_code_api"} | AgentConfiguration.DIRECT_API_AGENT_TYPES
        if agent_type in api_key_types and not cleaned.get("api_key"):
            existing = self.instance.get_api_key() if (self.instance and self.instance.pk) else ""
            if not existing:
                self.add_error("api_key", "An API key is required for this agent type.")
        return cleaned
