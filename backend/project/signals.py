"""Reliable signals — receivers run asynchronously via Celery.

Standard Django signals are synchronous and unreliable: a receiver failure
propagates back to the sender, and there is no delivery guarantee if the process
crashes after the database has committed. This module provides a
``ReliableSignal`` whose receivers are scheduled inside the current database
transaction and executed later as Celery tasks, so:

- if the transaction rolls back, the receiver tasks are never enqueued;
- if it commits, the tasks are guaranteed to be on the queue;
- delivery is at-least-once, so **every receiver must be idempotent**;
- arguments must be JSON-serializable — pass IDs, never model instances.

Adapted from Haki Benita's "Reliable Signals in Django"
(https://hakibenita.com/django-reliable-signals).
"""

from __future__ import annotations

import json
from functools import partial
from typing import Any

from celery import shared_task
from django.db import transaction
from django.dispatch import Signal
from django.utils.module_loading import import_string


@shared_task
def _dispatch_reliable_receiver(receiver_path: str, kwargs_json: str) -> None:
    """Import a receiver by dotted path and call it with the decoded kwargs."""
    receiver = import_string(receiver_path)
    receiver(**json.loads(kwargs_json))


class ReliableSignal(Signal):
    """A Django ``Signal`` whose receivers run asynchronously via Celery.

    Use :meth:`send_reliable` instead of ``send``. It must run inside (or under)
    a database transaction; the receiver tasks are scheduled on commit.
    """

    def send_reliable(self, sender: Any, **kwargs: Any) -> None:
        """Schedule every connected receiver to run after the current commit.

        ``kwargs`` must be JSON-serializable. Receivers are dispatched as Celery
        tasks by dotted import path, not through Django's synchronous fan-out, so
        each connected receiver must be an importable module-level function.
        """
        payload = json.dumps(kwargs)
        # Django 6's ``_live_receivers`` returns a ``(sync, async)`` pair of
        # receiver lists. This is a private API whose shape has changed across
        # Django versions — re-check it on every Django upgrade.
        sync_receivers, async_receivers = self._live_receivers(sender)
        for receiver in (*sync_receivers, *async_receivers):
            path = f"{receiver.__module__}.{receiver.__qualname__}"
            transaction.on_commit(partial(_dispatch_reliable_receiver.delay, path, payload))
