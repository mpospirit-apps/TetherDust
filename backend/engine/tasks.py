"""Celery tasks for scheduled report execution."""

import datetime
import decimal
import logging

from celery import shared_task
from django.utils import timezone

from engine.services import AgentService, CodebaseService, SystemConfigService, get


def _serialize_value(val: object) -> object:
    """Convert non-JSON-serializable SQL result values."""
    if isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
        return val.isoformat()
    if isinstance(val, decimal.Decimal):
        return float(val)
    if isinstance(val, datetime.timedelta):
        return val.total_seconds()
    return val


def _serialize_row(columns: list[str], row: list[object]) -> dict[str, object]:
    """Build a JSON-safe dict from a SQL result row."""
    return {col: _serialize_value(v) for col, v in zip(columns, row)}


logger = logging.getLogger(__name__)


@shared_task
def check_due_reports() -> None:
    """Periodic task: find due reports and dispatch individual execution tasks."""
    from .engines.report_engine import compute_next_run
    from .models import ReportDefinition

    now = timezone.now()

    # Initialize next_run_at for scheduled reports that don't have one yet
    # (safety net for reports created before the save-time computation was added)
    uninitialized = ReportDefinition.objects.filter(
        is_active=True,
        next_run_at__isnull=True,
    ).exclude(schedule_type="manual")
    for report in uninitialized:
        report.next_run_at = compute_next_run(report)
        report.save(update_fields=["next_run_at"])

    due_reports = ReportDefinition.objects.filter(
        is_active=True,
        next_run_at__lte=now,
    ).exclude(schedule_type="manual")

    count = 0
    for report in due_reports:
        execute_report_task.delay(report.pk)
        count += 1

    if count:
        logger.info("Dispatched %d due report(s).", count)


@shared_task(soft_time_limit=300, time_limit=360)
def execute_report_task(report_definition_id: str) -> None:
    """Execute a single report. Called by check_due_reports or manually."""
    from .engines.report_engine import execute_report
    from .models import ReportDefinition

    try:
        report = ReportDefinition.objects.get(pk=report_definition_id)
    except ReportDefinition.DoesNotExist:
        logger.warning("Report definition %s not found, skipping.", report_definition_id)
        return

    execution = execute_report(report, triggered_by=None)
    logger.info(
        "Report '%s' executed: %s (%d rows, %dms)",
        report.name,
        execution.status,
        execution.row_count or 0,
        execution.execution_time_ms or 0,
    )

    # Send email if delivery method is email and execution succeeded
    if execution.status == "success" and report.delivery_method == "email":
        recipients = (report.delivery_config or {}).get("email_recipients", [])
        if recipients:
            send_report_email_task.delay(execution.pk, recipients)


@shared_task(soft_time_limit=120, time_limit=150)
def send_report_email_task(execution_id: str, recipient_emails: list[str] | None = None) -> None:
    """Send report results via email. Called after execution or on user request."""
    from .models import ReportExecution

    try:
        execution = ReportExecution.objects.select_related("definition").get(pk=execution_id)
    except ReportExecution.DoesNotExist:
        logger.warning("Report execution %s not found, cannot send email.", execution_id)
        return

    if recipient_emails is None:
        config = execution.definition.delivery_config or {}
        recipient_emails = config.get("email_recipients", [])

    if not recipient_emails:
        logger.info("No email recipients for execution %s, skipping.", execution_id)
        return

    try:
        from .engines.email_service import send_report_email

        sent = send_report_email(execution_id, recipient_emails)
        if sent:
            logger.info("Report email sent for execution %s.", execution_id)
        else:
            logger.warning(
                "Report email not sent for execution %s (service returned False).", execution_id
            )
    except Exception:
        logger.exception("Failed to send report email for execution %s.", execution_id)


@shared_task
def check_due_dashboard_refreshes() -> None:
    """Periodic task: find dashboards needing chart data refresh."""
    from .models import Dashboard

    now = timezone.now()
    dashboards = (
        Dashboard.objects.filter(is_active=True, auto_refresh=True)
        .exclude(refresh_interval__isnull=True)
        .exclude(refresh_interval="")
    )

    from .models import Chart

    count = 0
    for dashboard in dashboards:
        if not dashboard.refresh_interval:
            continue
        try:
            interval_minutes = int(dashboard.refresh_interval)
        except ValueError:
            continue

        for chart in Chart.objects.filter(dashboard=dashboard, is_active=True):
            if chart.last_refreshed_at is None or (
                (now - chart.last_refreshed_at).total_seconds() > interval_minutes * 60
            ):
                refresh_single_chart.delay(chart.pk)
                count += 1

    if count:
        logger.info("Dispatched %d chart refresh(es).", count)


@shared_task
def sync_codex_auth_token() -> None:
    """Periodic: pull the live (refreshed) Codex credential back into the DB.

    Codex refreshes the ChatGPT session token in place in the persistent volume
    (see codex_api `_harvest_volume_auth`). This keeps the encrypted DB backup
    current so a cold volume always re-seeds from a fresh token, and warns when
    the credential is approaching expiry.
    """
    import os

    import httpx

    config = get(AgentService).get_active()
    if not config or config.agent_type != "codex":
        return

    config_url = config.service_url or ""
    codex_url = (
        config_url
        or get(SystemConfigService).get_value("codex_service_url", "")
        or os.environ.get("CODEX_SERVICE_URL", "")
    ).rstrip("/")
    if not codex_url:
        return

    from engine.agents.gateway import gateway_auth_headers

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{codex_url}/auth/token", headers=gateway_auth_headers())
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning("Could not fetch Codex auth token for sync", exc_info=True)
        return

    if not data.get("present"):
        return

    token = data.get("auth_token", "")
    if token and token != config.auth_token:
        config.auth_token = token
        config.save(update_fields=["auth_token", "updated_at"])
        logger.info("Synced refreshed Codex credential into the database.")

    expires_at = data.get("expires_at")
    if expires_at:
        try:
            remaining = datetime.datetime.fromisoformat(expires_at) - timezone.now()
        except ValueError:
            remaining = None
        if remaining is not None and remaining < datetime.timedelta(days=2):
            logger.warning(
                "Codex credential expires in %s — re-authentication may be needed soon.",
                remaining,
            )


@shared_task(soft_time_limit=120, time_limit=150)
def sync_codebase(codebase_id: str) -> None:
    """Sync a codebase so the agent can browse/search it.

    Remote (GitHub/GitLab): we don't clone. Sync resolves the default branch,
    fetches the recursive git tree, and caches the result so
    ``get_codebase_tree`` is fast and rate-limit friendly; file contents are
    fetched live by the MCP tools.

    Local: files are read live from disk by the MCP tools (no cached tree needed),
    so sync only refreshes the ccc semantic index used by ``search_codebase``.
    """
    from .integrations import ccc_client
    from .integrations.github_client import GitHubClient
    from .integrations.gitlab_client import GitLabClient
    from .integrations.tree_filter import filter_tree
    from .models import Codebase

    try:
        cb = Codebase.objects.get(pk=codebase_id)
    except Codebase.DoesNotExist:
        logger.warning("Codebase %s not found, skipping sync.", codebase_id)
        return

    cb.sync_status = Codebase.SYNC_SYNCING
    cb.sync_error = ""
    cb.save(update_fields=["sync_status", "sync_error", "updated_at"])

    try:
        if cb.provider == "local":
            if ccc_client.is_configured():
                result = ccc_client.index(get(CodebaseService).ccc_project(cb))
                logger.info("Indexed local codebase '%s' via ccc: %s", cb.name, result)
            else:
                logger.info(
                    "ccc not configured; local codebase '%s' is browsable but not searchable.",
                    cb.name,
                )
            cb.last_synced_at = timezone.now()
            cb.sync_status = Codebase.SYNC_OK
            cb.sync_error = ""
            cb.save(update_fields=["last_synced_at", "sync_status", "sync_error", "updated_at"])
            return

        if cb.provider == "gitlab":
            project = get(CodebaseService).project_path(cb)
            gl_client = GitLabClient(token=cb.access_token or None)
            default_branch = gl_client.get_project(project).get("default_branch") or "main"
            raw_tree = gl_client.get_tree(project, default_branch)
        else:
            owner, repo = get(CodebaseService).owner_repo(cb)
            gh_client = GitHubClient(token=cb.access_token or None)
            default_branch = gh_client.get_repo(owner, repo).get("default_branch") or "main"
            raw_tree = gh_client.get_tree(owner, repo, default_branch)

        tree = filter_tree(raw_tree)

        cb.default_branch = default_branch
        cb.cached_tree = tree
        cb.last_synced_at = timezone.now()
        cb.sync_status = Codebase.SYNC_OK
        cb.sync_error = ""
        cb.save(
            update_fields=[
                "default_branch",
                "cached_tree",
                "last_synced_at",
                "sync_status",
                "sync_error",
                "updated_at",
            ]
        )
        logger.info("Synced codebase '%s': %d files cached", cb.name, len(tree))
    except Exception as e:
        cb.sync_status = Codebase.SYNC_ERROR
        cb.sync_error = str(e)[:1000]
        cb.save(update_fields=["sync_status", "sync_error", "updated_at"])
        logger.error("Codebase sync failed for %s: %s", codebase_id, e)


@shared_task
def resync_codebases() -> None:
    """Periodic: re-sync every active codebase.

    Local codebases get their ccc semantic index refreshed; remote
    (GitHub/GitLab) codebases get their cached file tree refreshed, so
    the agent sees new commits without an admin clicking Sync.
    """
    from .models import Codebase

    ids = Codebase.objects.filter(is_active=True).values_list("pk", flat=True)
    for cb_id in ids:
        try:
            sync_codebase.delay(cb_id)
        except Exception:
            sync_codebase(cb_id)


@shared_task(soft_time_limit=60, time_limit=90)
def refresh_single_chart(chart_id: str) -> None:
    """Execute a chart's SQL query and cache the results."""
    from .engines.db_runner import run_query
    from .models import Chart

    try:
        chart = Chart.objects.select_related("database").get(pk=chart_id)
    except Chart.DoesNotExist:
        logger.warning("Chart %s not found, skipping refresh.", chart_id)
        return

    try:
        db_conn = chart.database
        columns, raw_rows = run_query(db_conn, chart.sql_query)
        rows = [_serialize_row(columns, row) for row in raw_rows]

        now = timezone.now()
        chart.cached_data = {
            "columns": columns,
            "rows": rows,
            "refreshed_at": now.isoformat(),
        }
        chart.last_refreshed_at = now
        chart.last_error = ""
        chart.save(update_fields=["cached_data", "last_refreshed_at", "last_error"])

        logger.info("Refreshed chart '%s' (id=%s): %d rows", chart.title, chart.pk, len(rows))
    except Exception as e:
        chart.last_error = str(e)
        chart.save(update_fields=["last_error"])
        logger.error("Failed to refresh chart %s: %s", chart_id, e)


@shared_task
def check_for_updates() -> None:
    """Periodic: poll GitHub Releases for the latest TetherDust release tag and
    cache it in SystemConfiguration for the Version management tab.

    Network/parse failures are swallowed — a failed check must never break the
    beat loop or the management.
    """
    from .integrations.github_client import GitHubClient, GitHubError
    from .version import (
        GITHUB_REPOSITORY,
        LATEST_CHECKED_AT_KEY,
        LATEST_RELEASE_URL_KEY,
        LATEST_VERSION_KEY,
    )

    owner, repo = GITHUB_REPOSITORY.split("/", 1)

    try:
        release = GitHubClient().get_latest_release(owner, repo)
    except GitHubError as exc:
        logger.warning("check_for_updates: GitHub lookup failed for %s/%s: %s", owner, repo, exc)
        return

    tag = (release.get("tag_name") or "").strip()
    if not tag:
        logger.warning("check_for_updates: latest release for %s/%s has no tag", owner, repo)
        return

    get(SystemConfigService).set_value(LATEST_VERSION_KEY, tag, value_type="string")
    get(SystemConfigService).set_value(
        LATEST_RELEASE_URL_KEY, release.get("html_url", ""), value_type="string"
    )
    get(SystemConfigService).set_value(
        LATEST_CHECKED_AT_KEY, timezone.now().isoformat(), value_type="string"
    )
    logger.info("check_for_updates: latest release for %s/%s is %s", owner, repo, tag)
