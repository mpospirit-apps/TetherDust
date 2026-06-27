"""Reliable-signal receivers for the engine app.

Receivers here run asynchronously via Celery (see ``project.signals``) with
at-least-once delivery, so every handler MUST be idempotent — a duplicate
delivery has to be a no-op.
"""

from __future__ import annotations

from django.dispatch import receiver

from .signals import report_execution_deleted


@receiver(report_execution_deleted)
def on_report_execution_deleted(execution_id: str, **kwargs: object) -> None:
    """Remove the on-disk result directory for a deleted report execution.

    Idempotent: ``delete_results`` no-ops when the directory is already gone, so
    a repeated delivery is harmless.
    """
    from .engines.result_storage import delete_results

    delete_results(execution_id)
