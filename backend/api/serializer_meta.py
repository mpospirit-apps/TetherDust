"""Base class for DRF ``ModelSerializer.Meta`` inner classes.

``rest_framework-stubs`` declares a ``ModelSerializer.Meta`` (with ``model`` /
``fields`` / ``read_only_fields`` …) that has **no runtime counterpart** — DRF
expects each serializer to define its own ``Meta`` from scratch. A type checker
that enforces override consistency (pyrefly) therefore flags every plain
``class Meta:`` as an inconsistent override of the stubbed parent.

Inheriting the stub's ``Meta`` under ``TYPE_CHECKING`` (and ``object`` at
runtime) tells the checker the override is intentional and consistent, while
keeping the runtime class exactly what DRF expects. Serializers use it as::

    class Meta(SerializerMeta):
        model = Foo
        fields = [...]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from rest_framework.serializers import ModelSerializer

    class SerializerMeta(ModelSerializer.Meta):
        # The stub types ``model`` as ``ClassVar[type[_MT]]`` — generic over the
        # serializer's own model TypeVar, which a plain nested ``Meta`` can't
        # satisfy. Re-declare it as ``ClassVar[Any]`` so a concrete ``model = Foo``
        # assigns cleanly while the class stays a subtype of the stubbed parent.
        model: ClassVar[Any]

else:
    SerializerMeta = object
