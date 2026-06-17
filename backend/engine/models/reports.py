"""ReportDefinition and ReportExecution models for scheduled SQL reports."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.contrib.auth.models import User
from django.db import models

from ..ids import generate_rex_id, generate_rpt_id

if TYPE_CHECKING:
    from .auth import Role

from .connections import DatabaseConnection


class ReportDefinition(models.Model):
    """Admin-configured SQL report template.

    Latest-execution lookups live in
    :class:`engine.services.report.ReportService`.
    """

    class Meta:
        verbose_name = "report definition"
        verbose_name_plural = "report definitions"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "name"], name="idx_reportdef_active_name"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["name"], name="uq_%(class)s_name"),
        ]

    SCHEDULE_TYPE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("manual", "Manual"),
        ("interval", "Every N Minutes/Hours"),
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
    ]

    DELIVERY_METHOD_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("in_app", "In-App"),
        ("email", "Email"),
        ("slack", "Slack"),
        ("teams", "Microsoft Teams"),
    ]

    __prefix__: ClassVar[str] = "rpt"

    # Type-only annotations (reverse manager + view-attached attribute)
    executions: models.Manager[ReportExecution]
    latest_exec: ReportExecution | None

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_rpt_id, editable=False)

    # Time
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # State
    is_active = models.BooleanField(verbose_name="is active", default=True)

    # Domain
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    sql_query = models.TextField(
        verbose_name="SQL query", help_text="Read-only SELECT or WITH query"
    )
    schedule_type = models.CharField(
        verbose_name="schedule type",
        max_length=20,
        choices=SCHEDULE_TYPE_CHOICES,
        default="manual",
    )
    schedule_interval_minutes = models.IntegerField(
        verbose_name="schedule interval minutes",
        null=True,
        blank=True,
        help_text="Run every N minutes (for interval schedule)",
    )
    schedule_time = models.TimeField(
        verbose_name="schedule time",
        null=True,
        blank=True,
        help_text="Time of day for scheduled runs",
    )
    schedule_day_of_week = models.IntegerField(
        verbose_name="schedule day of week",
        null=True,
        blank=True,
        help_text="0=Monday .. 6=Sunday (for weekly)",
    )
    schedule_day_of_month = models.IntegerField(
        verbose_name="schedule day of month", null=True, blank=True, help_text="1-28 (for monthly)"
    )
    next_run_at = models.DateTimeField(
        verbose_name="next run at", null=True, blank=True, help_text="Computed next execution time"
    )
    delivery_method = models.CharField(
        verbose_name="delivery method",
        max_length=20,
        choices=DELIVERY_METHOD_CHOICES,
        default="in_app",
    )
    delivery_config = models.JSONField(
        verbose_name="delivery config",
        default=dict,
        blank=True,
        help_text="Future: email addresses, webhook URLs",
    )

    # Relations
    database = models.ForeignKey(
        DatabaseConnection, on_delete=models.PROTECT, related_name="reports"
    )
    allowed_roles: models.ManyToManyField[Role, Role] = models.ManyToManyField(
        "Role", blank=True, related_name="allowed_reports"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_reports"
    )

    def __str__(self) -> str:
        return self.name


class ReportExecution(models.Model):
    """Single run of a report with results and metadata.

    Result loading lives in :class:`engine.services.report.ReportService`.
    """

    class Meta:
        verbose_name = "report execution"
        verbose_name_plural = "report executions"
        ordering = ["-started_at"]
        indexes = [
            models.Index(
                fields=["definition", "status", "-started_at"],
                name="idx_%(class)s_def_status",
            ),
        ]

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    __prefix__: ClassVar[str] = "rex"

    # Identifiers
    id = models.CharField(max_length=64, primary_key=True, default=generate_rex_id, editable=False)

    # Time
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(verbose_name="completed at", null=True, blank=True)

    # State
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")

    # Domain
    execution_time_ms = models.IntegerField(verbose_name="execution time ms", null=True, blank=True)
    row_count = models.IntegerField(verbose_name="row count", null=True, blank=True)
    result_file_path = models.CharField(
        verbose_name="result file path", max_length=255, blank=True, default=""
    )
    error_message = models.TextField(verbose_name="error message", blank=True)

    # Relations
    definition = models.ForeignKey(
        ReportDefinition, on_delete=models.CASCADE, related_name="executions"
    )
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.definition.name} — {self.status} ({self.started_at})"
