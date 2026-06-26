"""Serializers for v1 of the SPA-facing API."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class LoginSerializer(serializers.Serializer[Any]):
    """Validates the username/password pair posted to the login endpoint."""

    username = serializers.CharField()
    password = serializers.CharField(style={"input_type": "password"}, trim_whitespace=False)
