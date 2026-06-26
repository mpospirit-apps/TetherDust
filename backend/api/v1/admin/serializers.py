"""Serializers for the admin (staff) API."""

from __future__ import annotations

from typing import Any

from engine.models import DatabaseConnection
from rest_framework import serializers

from api.serializer_meta import SerializerMeta


class DatabaseConnectionSerializer(serializers.ModelSerializer[DatabaseConnection]):
    """CRUD serializer for DatabaseConnection.

    ``password`` is write-only and stored via the model's ``EncryptedCharField``
    (encrypted at rest). A blank/omitted password on update keeps the existing
    credential, mirroring the legacy ``DatabaseConnectionForm``.
    """

    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={"input_type": "password"},
    )

    class Meta(SerializerMeta):
        model = DatabaseConnection
        fields = [
            "id",
            "name",
            "description",
            "engine",
            "host",
            "port",
            "database",
            "username",
            "password",
            "connection_string",
            "extra_options",
            "read_only",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def create(self, validated_data: Any) -> DatabaseConnection:
        password = validated_data.pop("password", "")
        instance = DatabaseConnection(**validated_data)
        if password:
            instance.password = password
        instance.save()
        return instance

    def update(self, instance: DatabaseConnection, validated_data: Any) -> DatabaseConnection:
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:  # only overwrite when a non-empty password is supplied
            instance.password = password
        instance.save()
        return instance
