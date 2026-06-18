"""Signal handlers for the chat app."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import ReportExecution

logger = logging.getLogger(__name__)


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
    """Delete result files from disk when a ReportExecution is deleted."""
    if instance.result_file_path:
        from .engines.result_storage import delete_results

        delete_results(instance.pk)
