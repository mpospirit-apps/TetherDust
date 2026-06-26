"""Signal handlers for the chat app."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from project.signals import ReliableSignal

from .models import ReportExecution

logger = logging.getLogger(__name__)

# Reliable signals — receivers live in ``engine/receivers.py`` and run via Celery
# after the emitting transaction commits. Emit with ``send_reliable``.
report_execution_deleted = ReliableSignal()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender: type[Any], instance: User, created: bool, **kwargs: object) -> None:
    """Create a UserProfile for every new User.

    Superusers and staff get the Admin role (if it exists).
    Regular users get a profile with no role (no permissions).
    """
    from .models import Role, UserProfile

    if created:
        role = None
        if instance.is_superuser or instance.is_staff:
            role = Role.objects.filter(name="Admin").first()
        UserProfile.objects.create(user=instance, role=role)
        logger.info(
            "Auto-created UserProfile for user=%s, role=%s",
            instance.username,
            role,
        )


@receiver(post_delete, sender=ReportExecution)
def cleanup_report_results(sender: type[Any], instance: ReportExecution, **kwargs: object) -> None:
    """Reliably clean up result files after a ReportExecution delete commits.

    Emitting from ``post_delete`` (rather than a service method) covers every
    delete path — API, cascade, admin — and fires inside the delete's
    transaction, so the cleanup is scheduled on commit and skipped on rollback.
    The on-disk removal happens in
    ``engine.receivers.on_report_execution_deleted`` and is idempotent.
    """
    if instance.result_file_path:
        report_execution_deleted.send_reliable(sender=None, execution_id=instance.pk)
