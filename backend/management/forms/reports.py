"""Forms for report definitions and scheduling."""

from django import forms
from engine.forms.base import _BaseForm
from engine.models import ReportDefinition, Role

INTERVAL_CHOICES = [
    ("", "---------"),
    ("5", "Every 5 minutes"),
    ("10", "Every 10 minutes"),
    ("15", "Every 15 minutes"),
    ("30", "Every 30 minutes"),
    ("60", "Every 1 hour"),
    ("120", "Every 2 hours"),
    ("360", "Every 6 hours"),
    ("720", "Every 12 hours"),
]

TIME_CHOICES = [("", "---------")] + [
    (f"{h:02d}:{m:02d}", f"{h:02d}:{m:02d}") for h in range(24) for m in (0, 30)
]

DAY_OF_WEEK_CHOICES = [
    ("", "---------"),
    ("0", "Monday"),
    ("1", "Tuesday"),
    ("2", "Wednesday"),
    ("3", "Thursday"),
    ("4", "Friday"),
    ("5", "Saturday"),
    ("6", "Sunday"),
]

DAY_OF_MONTH_CHOICES = [("", "---------")] + [(str(d), str(d)) for d in range(1, 29)]


class ReportDefinitionForm(_BaseForm):
    schedule_interval_minutes = forms.TypedChoiceField(
        choices=INTERVAL_CHOICES,
        coerce=int,
        required=False,
        empty_value=None,
        label="Run interval",
    )
    schedule_time = forms.TypedChoiceField(
        choices=TIME_CHOICES,
        required=False,
        empty_value=None,
        label="Time of day (UTC)",
    )
    schedule_day_of_week = forms.TypedChoiceField(
        choices=DAY_OF_WEEK_CHOICES,
        coerce=int,
        required=False,
        empty_value=None,
        label="Day of week",
    )
    schedule_day_of_month = forms.TypedChoiceField(
        choices=DAY_OF_MONTH_CHOICES,
        coerce=int,
        required=False,
        empty_value=None,
        label="Day of month",
    )
    allowed_roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Allowed Roles",
        help_text="Roles that can view this report's results",
    )
    email_recipients = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "one@example.com\ntwo@example.com",
            }
        ),
        label="Email Recipients",
        help_text="One email address per line. Recipients receive the report on each scheduled run.",  # noqa: E501
    )

    class Meta:
        model = ReportDefinition
        fields = [
            "name",
            "description",
            "database",
            "sql_query",
            "schedule_type",
            "schedule_interval_minutes",
            "schedule_time",
            "schedule_day_of_week",
            "schedule_day_of_month",
            "delivery_method",
            "is_active",
            "allowed_roles",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "sql_query": forms.Textarea(
                attrs={
                    "rows": 12,
                    "style": "font-family: 'Space Mono', monospace; font-size: 13px;",
                    "placeholder": "SELECT column1, column2\nFROM table_name\nWHERE condition",
                }
            ),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.schedule_time:
                t = self.instance.schedule_time
                # Snap to nearest 30-min slot for the dropdown
                m = 0 if t.minute < 15 else 30 if t.minute < 45 else 0
                h = t.hour if t.minute < 45 else (t.hour + 1) % 24
                self.initial["schedule_time"] = f"{h:02d}:{m:02d}"
            if self.instance.schedule_day_of_week is not None:
                self.initial["schedule_day_of_week"] = str(self.instance.schedule_day_of_week)
            if self.instance.schedule_day_of_month is not None:
                self.initial["schedule_day_of_month"] = str(self.instance.schedule_day_of_month)
            if self.instance.schedule_interval_minutes is not None:
                self.initial["schedule_interval_minutes"] = str(
                    self.instance.schedule_interval_minutes
                )
            # Populate email recipients from delivery_config
            config = self.instance.delivery_config or {}
            recipients = config.get("email_recipients", [])
            if recipients:
                self.initial["email_recipients"] = "\n".join(recipients)

    def clean_email_recipients(self) -> list[str]:
        val = self.cleaned_data.get("email_recipients", "").strip()
        if not val:
            return []
        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.core.validators import validate_email

        emails = []
        errors = []
        for line in val.splitlines():
            email = line.strip()
            if not email:
                continue
            try:
                validate_email(email)
                emails.append(email)
            except DjangoValidationError:
                errors.append(f"Invalid email: {email}")
        if errors:
            raise forms.ValidationError(errors)
        return emails

    def clean_schedule_time(self) -> object:
        val = self.cleaned_data.get("schedule_time")
        if not val:
            return None
        from datetime import time as dt_time

        h, m = val.split(":")
        return dt_time(int(h), int(m))

    def clean_sql_query(self) -> str:
        from engine.engines.report_engine import validate_sql

        sql = self.cleaned_data.get("sql_query", "")
        db = self.cleaned_data.get("database")
        error = validate_sql(sql, engine=db.engine if db else None)
        if error:
            raise forms.ValidationError(error)
        return str(sql)

    def save(self, commit: bool = True) -> object:
        instance = super().save(commit=False)
        # Merge email recipients into delivery_config
        config = instance.delivery_config or {}
        config["email_recipients"] = self.cleaned_data.get("email_recipients", [])
        instance.delivery_config = config
        if commit:
            instance.save()
            self.save_m2m()
        return instance
