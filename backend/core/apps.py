from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_builtin_mcp(sender: object, using: str, **kwargs: object) -> None:
    """Ensure the built-in MCP server + tool rows exist after migrations."""
    from .builtin_mcp import ensure_builtin_mcp

    ensure_builtin_mcp(using=using)


def _seed_shipped_docs(sender: object, using: str, **kwargs: object) -> None:
    """Register the shipped docs + sync filesystem folders after migrations."""
    from .builtin_docs import ensure_shipped_docs

    ensure_shipped_docs(using=using)


class CoreConfig(AppConfig):
    name = "core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from . import signals  # noqa: F401

        post_migrate.connect(_seed_builtin_mcp, sender=self)
        post_migrate.connect(_seed_shipped_docs, sender=self)
