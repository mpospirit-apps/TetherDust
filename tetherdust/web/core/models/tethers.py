"""Tether and TetherVersion models for codebase × database visual links."""

from django.contrib.auth.models import User
from django.db import models

from .connections import Codebase, DocumentationSource


class Tether(models.Model):
    """A codebase × database visual link, with N generated versions."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    codebase = models.ForeignKey(
        Codebase,
        on_delete=models.PROTECT,
        related_name="tethers",
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
