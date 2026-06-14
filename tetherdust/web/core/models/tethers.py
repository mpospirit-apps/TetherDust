"""Tether and TetherVersion models for codebase × database visual links."""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models

from .connections import Codebase, DocumentationSource


class Tether(models.Model):
    """A code × database visual link, with N generated versions.

    The code side is either a live ``Codebase`` repository or a codebase
    ``DocumentationSource`` — exactly one of the two is set.
    """

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    codebase = models.ForeignKey(
        Codebase,
        on_delete=models.PROTECT,
        related_name="tethers",
        null=True,
        blank=True,
        help_text="Code side: a live codebase repository (mutually exclusive with codebase doc).",
    )
    codebase_doc_source = models.ForeignKey(
        DocumentationSource,
        on_delete=models.PROTECT,
        related_name="tethers_as_codebase",
        limit_choices_to={"doc_type": DocumentationSource.DocType.CODEBASE},
        null=True,
        blank=True,
        help_text="Code side: a codebase documentation source (mutually exclusive with codebase).",
    )
    database_doc_source = models.ForeignKey(
        DocumentationSource,
        on_delete=models.PROTECT,
        related_name="tethers_as_database",
        limit_choices_to={"doc_type": DocumentationSource.DocType.DATABASE},
    )
    current_version = models.ForeignKey(
        "TetherVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Latest successful run; what the viewer renders.",
    )
    allowed_roles = models.ManyToManyField("Role", blank=True, related_name="allowed_tethers")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_tethers"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Tether"
        verbose_name_plural = "Tethers"

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """Require exactly one code source: a codebase repo or a codebase doc."""
        if bool(self.codebase_id) == bool(self.codebase_doc_source_id):
            raise ValidationError(
                "Pick exactly one code source: a codebase repository or a codebase "
                "documentation source."
            )

    @property
    def uses_codebase_repo(self) -> bool:
        """True when the code side is a live codebase repository."""
        return self.codebase_id is not None

    @property
    def source_name(self) -> str:
        """Display name of the code side, whichever source type it is."""
        if self.codebase_id:
            return self.codebase.name
        if self.codebase_doc_source_id:
            return self.codebase_doc_source.folder_name
        return ""


class TetherVersion(models.Model):
    """One generation run of a Tether."""

    STATUS_CHOICES = [
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    tether = models.ForeignKey(Tether, on_delete=models.CASCADE, related_name="versions")
    version_number = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    execution_time_ms = models.IntegerField(null=True, blank=True)
    graph_json = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    agent_log_excerpt = models.TextField(
        blank=True, help_text="Last ~4kB of Codex stream for debugging"
    )
    prompt_used = models.TextField(blank=True)
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-version_number"]
        unique_together = [("tether", "version_number")]
        verbose_name = "Tether Version"
        verbose_name_plural = "Tether Versions"

    def __str__(self) -> str:
        return f"{self.tether.name} v{self.version_number} ({self.status})"
