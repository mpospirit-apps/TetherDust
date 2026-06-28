"""ReportService — latest-execution selection and result-loading guards."""

from __future__ import annotations

import pytest
from engine.services import ReportService, get
from freezegun import freeze_time
from model_bakery import baker

pytestmark = pytest.mark.django_db


@pytest.fixture
def reports() -> ReportService:
    return get(ReportService)


def test_get_latest_execution_picks_most_recent_success(reports: ReportService) -> None:
    definition = baker.make("engine.ReportDefinition")
    with freeze_time("2026-01-01"):
        baker.make("engine.ReportExecution", definition=definition, status="success")
    with freeze_time("2026-02-01"):
        newer = baker.make("engine.ReportExecution", definition=definition, status="success")
    # A later *failed* run must not win.
    with freeze_time("2026-03-01"):
        baker.make("engine.ReportExecution", definition=definition, status="error")

    assert reports.get_latest_execution(definition) == newer


def test_get_latest_execution_none_when_no_success(reports: ReportService) -> None:
    definition = baker.make("engine.ReportDefinition")
    baker.make("engine.ReportExecution", definition=definition, status="error")
    assert reports.get_latest_execution(definition) is None


def test_result_accessors_empty_without_file(reports: ReportService) -> None:
    execution = baker.make("engine.ReportExecution", result_file_path="")
    assert reports.column_names(execution) == []
    assert reports.result_data(execution) == []
