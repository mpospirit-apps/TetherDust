"""ReportDefinition and ReportExecution models for scheduled SQL reports."""

from django.contrib.auth.models import User
from django.db import models

from .connections import DatabaseConnection


class ReportDefinition(models.Model):
    """Admin-configured SQL report template."""

    SCHEDULE_TYPE_CHOICES = [
        ("manual", "Manual"),
        ("interval", "Every N Minutes/Hours"),
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
    ]

    DELIVERY_METHOD_CHOICES = [
        ("in_app", "In-App"),
        ("email", "Email"),
        ("slack", "Slack"),
        ("teams", "Microsoft Teams"),
    ]

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    database = models.ForeignKey(
        DatabaseConnection, on_delete=models.PROTECT, related_name="reports"
    )
    sql_query = models.TextField(help_text="Read-only SELECT or WITH query")
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPE_CHOICES, default="manual")
    schedule_interval_minutes = models.IntegerField(
        null=True,
        blank=True,
        help_text="Run every N minutes (for interval schedule)",
    )
    schedule_time = models.TimeField(
        null=True, blank=True, help_text="Time of day for scheduled runs"
    )
    schedule_day_of_week = models.IntegerField(
        null=True, blank=True, help_text="0=Monday .. 6=Sunday (for weekly)"
    )
    schedule_day_of_month = models.IntegerField(
        null=True, blank=True, help_text="1-28 (for monthly)"
    )
    next_run_at = models.DateTimeField(
        null=True, blank=True, help_text="Computed next execution time"
    )
    delivery_method = models.CharField(
        max_length=20, choices=DELIVERY_METHOD_CHOICES, default="in_app"
    )
    delivery_config = models.JSONField(
        default=dict, blank=True, help_text="Future: email addresses, webhook URLs"
    )
    allowed_roles = models.ManyToManyField("Role", blank=True, related_name="allowed_reports")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_reports"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Report Definition"
        verbose_name_plural = "Report Definitions"

    def __str__(self) -> str:
        return self.name

    def get_latest_execution(self) -> "ReportExecution | None":
        """Return the most recent successful execution, or None."""
        return self.executions.filter(status="success").order_by("-started_at").first()


class ReportExecution(models.Model):
    """Single run of a report with results and metadata."""

    STATUS_CHOICES = [
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    definition = models.ForeignKey(
        ReportDefinition, on_delete=models.CASCADE, related_name="executions"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    execution_time_ms = models.IntegerField(null=True, blank=True)
    row_count = models.IntegerField(null=True, blank=True)
    result_file_path = models.CharField(max_length=255, blank=True, default="")
    error_message = models.TextField(blank=True)
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def column_names(self) -> list[str]:
        """Load column names from filesystem storage."""
        if not self.result_file_path:
            return []
        from ..engines.result_storage import load_meta

        meta = load_meta(self.pk)
        return meta["column_names"] if meta else []

    @property
    def result_data(self) -> list[dict[str, object]]:
        """Load result rows from filesystem storage."""
        if not self.result_file_path:
            return []
        from ..engines.result_storage import load_rows

        return load_rows(self.pk)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Report Execution"
        verbose_name_plural = "Report Executions"

    def __str__(self) -> str:
        return f"{self.definition.name} — {self.status} ({self.started_at})"
