"""Report service: latest execution and result loading."""

from __future__ import annotations

from ..models.reports import ReportDefinition, ReportExecution


class ReportService:
    """Operations on :class:`ReportDefinition` / :class:`ReportExecution`."""

    def get_latest_execution(self, definition: ReportDefinition) -> ReportExecution | None:
        """Return the most recent successful execution, or None."""
        return definition.executions.filter(status="success").order_by("-started_at").first()

    def column_names(self, execution: ReportExecution) -> list[str]:
        """Load column names from filesystem storage."""
        if not execution.result_file_path:
            return []
        from ..engines.result_storage import load_meta

        meta = load_meta(execution.pk)
        return meta["column_names"] if meta else []

    def result_data(self, execution: ReportExecution) -> list[list[object]]:
        """Load result rows from filesystem storage."""
        if not execution.result_file_path:
            return []
        from ..engines.result_storage import load_rows

        return load_rows(execution.pk)
