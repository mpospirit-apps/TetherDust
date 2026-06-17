"""Minimal service registry.

Services are stateless classes; ``get(SomeService)`` returns a process-wide
cached instance. This mirrors a dependency-injection ``get`` without pulling in
a framework — callers ask for a service by type and get a singleton back.
"""

from __future__ import annotations

from typing import TypeVar, cast

T = TypeVar("T")

_instances: dict[type, object] = {}


def get(service_cls: type[T]) -> T:
    """Return the cached singleton instance of ``service_cls``."""
    instance = _instances.get(service_cls)
    if instance is None:
        instance = service_cls()
        _instances[service_cls] = instance
    return cast(T, instance)
