"""System settings admin API: general config, SMTP config, and an SMTP test.

Settings live in the typed key-value :class:`SystemConfiguration` store
(`SystemConfigService`), not a model — so these are plain ``APIView``s mirroring
the legacy ``general_settings_view`` / ``smtp_settings_view`` / ``smtp_test_view``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, cast

from django.core.mail import EmailMessage
from engine.models import encrypt_value
from engine.services import SystemConfigService, get
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsStaffUser

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


def _cfg() -> SystemConfigService:
    return get(SystemConfigService)


class GeneralSettingsSerializer(serializers.Serializer[Any]):
    docgen_timeout = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    doclibgen_timeout = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    chartgen_timeout = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class GeneralSettingsView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request: Request) -> Response:
        cfg = _cfg()
        return Response(
            {
                "docgen_timeout": cfg.get_value(
                    "docgen_timeout", int(os.getenv("DOCGEN_TIMEOUT", "1800"))
                ),
                "doclibgen_timeout": cfg.get_value(
                    "doclibgen_timeout", int(os.getenv("DOCLIBGEN_TIMEOUT", "3600"))
                ),
                "chartgen_timeout": cfg.get_value(
                    "chartgen_timeout", int(os.getenv("CHARTGEN_TIMEOUT", "1800"))
                ),
            }
        )

    def put(self, request: Request) -> Response:
        serializer = GeneralSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        cfg = _cfg()
        for key in ("docgen_timeout", "doclibgen_timeout", "chartgen_timeout"):
            val = data.get(key)
            if val is not None:
                cfg.set_value(key, val, value_type="integer")
        return self.get(request)


class SmtpSettingsSerializer(serializers.Serializer[Any]):
    smtp_host = serializers.CharField(required=False, allow_blank=True, default="")
    smtp_port = serializers.IntegerField(required=False, allow_null=True)
    smtp_username = serializers.CharField(required=False, allow_blank=True, default="")
    smtp_password = serializers.CharField(
        required=False, allow_blank=True, default="", style={"input_type": "password"}
    )
    smtp_use_tls = serializers.BooleanField(required=False, default=True)
    smtp_from_email = serializers.EmailField(required=False, allow_blank=True, default="")
    email_max_rows = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class SmtpSettingsView(APIView):
    permission_classes = [IsStaffUser]

    def get(self, request: Request) -> Response:
        cfg = _cfg()
        return Response(
            {
                "smtp_host": cfg.get_value("smtp_host", ""),
                "smtp_port": cfg.get_value("smtp_port", 587),
                "smtp_username": cfg.get_value("smtp_username", ""),
                "smtp_use_tls": cfg.get_value("smtp_use_tls", True),
                "smtp_from_email": cfg.get_value("smtp_from_email", ""),
                "email_max_rows": cfg.get_value("email_max_rows", 10000),
                # Never return the password; just whether one is stored.
                "has_password": bool(cfg.get_value("smtp_password", "")),
            }
        )

    def put(self, request: Request) -> Response:
        serializer = SmtpSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        cfg = _cfg()
        for key in ("smtp_host", "smtp_username", "smtp_from_email"):
            cfg.set_value(key, data.get(key, ""), value_type="string")
        port = data.get("smtp_port")
        if port is not None:
            cfg.set_value("smtp_port", port, value_type="integer")
        cfg.set_value("smtp_use_tls", data.get("smtp_use_tls", True), value_type="boolean")
        pw = data.get("smtp_password", "")
        if pw:
            cfg.set_value("smtp_password", encrypt_value(pw), value_type="string")
        email_max_rows = data.get("email_max_rows")
        if email_max_rows is not None:
            cfg.set_value("email_max_rows", email_max_rows, value_type="integer")
        return self.get(request)


class SmtpTestView(APIView):
    permission_classes = [IsStaffUser]

    def post(self, request: Request) -> Response:
        """Send a test email to the logged-in admin's address."""
        from engine.engines.email_service import get_email_connection, get_smtp_config

        user = cast("AbstractUser", request.user)
        user_email = user.email
        if not user_email:
            return Response(
                {"error": "Your account has no email address. Set one in user settings first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config = get_smtp_config()
        if not config:
            return Response(
                {"error": "SMTP is not configured. Save your SMTP settings first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        connection = get_email_connection(config)
        if not connection:
            return Response(
                {"error": "Could not create SMTP connection."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            sender = cast("str | None", config["from_email"] or config["username"])
            email = EmailMessage(
                subject="TetherDust — SMTP Test",
                body="<p>This is a test email from TetherDust. Your SMTP configuration is working correctly.</p>",  # noqa: E501
                from_email=sender,
                to=[user_email],
                connection=connection,
            )
            email.content_subtype = "html"
            email.send()
            return Response({"message": f"Test email sent to {user_email}."})
        except Exception as exc:
            return Response(
                {"error": f"Failed to send: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            try:
                connection.close()
            except Exception:
                pass
