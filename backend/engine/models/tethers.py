"""Tether and TetherVersion models for codebase × database visual links."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.contrib.auth.models import User
from django.db import models

from ..ids import generate_tth_id, generate_tvr_id

if TYPE_CHECKING:
    from .auth import Role

from .connections import Codebase, DocumentationSource


class Tether(models.Model):
    """A code × database visual link, with N generated versions.

    The code side is either a live ``Codebase`` repository or a codebase
    ``DocumentationSource`` — exactly one of the two is set.
    """

    class Meta:
        verbose_name = "tether"
        verbose_name_plural = "tethers"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "name"], name="idx_%(class)s_active_name"),
        ]

    __prefix__: ClassVar[str] = "tth"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_tth_id, editable=False)

    # Time
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # State
    is_active = models.BooleanField(verbose_name="is active", default=True)

    # Domain
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Relations
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
    allowed_roles: models.ManyToManyField[Role, Role] = models.ManyToManyField(
        "Role", blank=True, related_name="allowed_tethers"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_tethers"
    )

    def __str__(self) -> str:
        return self.name


class TetherVersion(models.Model):
    """One generation run of a Tether."""

    class Meta:
        verbose_name = "tether version"
        verbose_name_plural = "tether versions"
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["tether", "version_number"], name="uq_%(class)s_tether_version"
            ),
        ]

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    __prefix__: ClassVar[str] = "tvr"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_tvr_id, editable=False)

    # Time
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(verbose_name="completed at", null=True, blank=True)

    # State
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")

    # Domain
    version_number = models.IntegerField(verbose_name="version number")
    execution_time_ms = models.IntegerField(verbose_name="execution time ms", null=True, blank=True)
    graph_json = models.JSONField(verbose_name="graph JSON", default=dict, blank=True)
    error_message = models.TextField(verbose_name="error message", blank=True)
    agent_log_excerpt = models.TextField(
        verbose_name="agent log excerpt",
        blank=True,
        help_text="Last ~4kB of Codex stream for debugging",
    )
    prompt_used = models.TextField(verbose_name="prompt used", blank=True)

    # Relations
    tether = models.ForeignKey(Tether, on_delete=models.CASCADE, related_name="versions")
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.tether.name} v{self.version_number} ({self.status})"
