"""Forms for dashboards and charts."""

from core.forms.base import _BaseForm
from core.models import Chart, Dashboard, Role
from django import forms


class DashboardForm(_BaseForm):
    allowed_roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Allowed Roles",
        help_text="Roles that can view this dashboard",
    )

    class Meta:
        model = Dashboard
        fields = [
            "name",
            "description",
            "is_active",
            "auto_refresh",
            "refresh_interval",
            "allowed_roles",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class ChartForm(_BaseForm):
    class Meta:
        model = Chart
        fields = [
            "title",
            "description",
            "database",
            "sql_query",
            "custom_d3_code",
            "width",
            "height",
            "position",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "sql_query": forms.Textarea(
                attrs={
                    "rows": 10,
                    "style": "font-family: 'Space Mono', monospace; font-size: 13px;",
                    "placeholder": "SELECT column1, column2\nFROM table_name\nWHERE condition",
                }
            ),
            "custom_d3_code": forms.Textarea(
                attrs={
                    "rows": 20,
                    "style": "font-family: 'Space Mono', monospace; font-size: 13px;",
                    "placeholder": "// data: array of row objects\n// container: DOM element\n// d3: the d3 library\n\nconst svg = d3.select(container)\n  .append('svg')\n  .attr('width', container.clientWidth)\n  .attr('height', container.clientHeight);",  # noqa: E501
                }
            ),
        }

    def clean_sql_query(self) -> str:
        from core.engines.report_engine import validate_sql

        sql = self.cleaned_data.get("sql_query", "")
        db = self.cleaned_data.get("database")
        error = validate_sql(sql, engine=db.engine if db else None)
        if error:
            raise forms.ValidationError(error)
        return sql
