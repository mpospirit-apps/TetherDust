"""SMTP and general system settings."""

import os
from typing import cast

from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from engine.models import SystemConfiguration
from engine.services import SystemConfigService, get

from management.views._helpers import staff_required

from ..forms import GeneralSettingsForm, SMTPSettingsForm


@staff_required
def smtp_settings_view(request: HttpRequest) -> HttpResponse:
    from engine.models import encrypt_value

    if request.method == "POST":
        form = SMTPSettingsForm(request.POST)
        if form.is_valid():
            for key in ("smtp_host", "smtp_username", "smtp_from_email"):
                val = form.cleaned_data.get(key, "")
                get(SystemConfigService).set_value(key, val, value_type="string")
            port = form.cleaned_data.get("smtp_port")
            if port is not None:
                get(SystemConfigService).set_value("smtp_port", port, value_type="integer")
            get(SystemConfigService).set_value(
                "smtp_use_tls",
                form.cleaned_data.get("smtp_use_tls", True),
                value_type="boolean",
            )
            pw = form.cleaned_data.get("smtp_password", "")
            if pw:
                get(SystemConfigService).set_value(
                    "smtp_password",
                    encrypt_value(pw),
                    value_type="string",
                )
            email_max_rows = form.cleaned_data.get("email_max_rows")
            if email_max_rows is not None:
                get(SystemConfigService).set_value(
                    "email_max_rows", email_max_rows, value_type="integer"
                )
            return redirect("management:settings_email")
    else:
        initial = {
            "smtp_host": get(SystemConfigService).get_value("smtp_host", ""),
            "smtp_port": get(SystemConfigService).get_value("smtp_port", 587),
            "smtp_username": get(SystemConfigService).get_value("smtp_username", ""),
            "smtp_use_tls": get(SystemConfigService).get_value("smtp_use_tls", True),
            "smtp_from_email": get(SystemConfigService).get_value("smtp_from_email", ""),
            "email_max_rows": get(SystemConfigService).get_value("email_max_rows", 10000),
        }
        has_password = bool(get(SystemConfigService).get_value("smtp_password", ""))
        form = SMTPSettingsForm(initial=initial)
        if has_password:
            form.fields["smtp_password"].widget.attrs["placeholder"] = (
                "••••••••  (leave blank to keep)"
            )

    return render(
        request,
        "management/sysconfig/smtp_settings.html",
        {
            "form": form,
            "section": "settings",
        },
    )


@staff_required
@require_POST
def smtp_test_view(request: HttpRequest) -> HttpResponse:
    """Send a test email to the logged-in admin's address."""
    from engine.engines.email_service import get_email_connection, get_smtp_config

    user_email = cast(User, request.user).email
    if not user_email:
        return JsonResponse(
            {"error": "Your account has no email address. Set one in user settings first."},
            status=400,
        )

    config = get_smtp_config()
    if not config:
        return JsonResponse(
            {"error": "SMTP is not configured. Save your SMTP settings first."}, status=400
        )

    connection = get_email_connection(config)
    if not connection:
        return JsonResponse({"error": "Could not create SMTP connection."}, status=500)

    try:
        from django.core.mail import EmailMessage

        email = EmailMessage(
            subject="TetherDust — SMTP Test",
            body="<p>This is a test email from TetherDust. Your SMTP configuration is working correctly.</p>",  # noqa: E501
            from_email=cast(str | None, config["from_email"]) or cast(str, config["username"]),
            to=[user_email],
            connection=connection,
        )
        email.content_subtype = "html"
        email.send()
        return JsonResponse({"message": f"Test email sent to {user_email}."})
    except Exception as e:
        return JsonResponse({"error": f"Failed to send: {e}"}, status=500)
    finally:
        try:
            connection.close()
        except Exception:
            pass


@staff_required
def general_settings_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = GeneralSettingsForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            for key in ("codex_service_url", "mcp_base_url"):
                get(SystemConfigService).set_value(key, cd.get(key, "") or "", value_type="string")
            for key in ("docgen_timeout", "doclibgen_timeout", "chartgen_timeout"):
                val = cd.get(key)
                if val is not None:
                    get(SystemConfigService).set_value(key, val, value_type="integer")
            for key in ("max_row_limit", "hot_reload_interval"):
                val = cd.get(key)
                if val is not None:
                    get(SystemConfigService).set_value(key, val, value_type="integer")
                else:
                    SystemConfiguration.objects.filter(key=key).delete()
            return redirect("management:settings")
    else:
        initial = {
            "codex_service_url": get(SystemConfigService).get_value(
                "codex_service_url", os.getenv("CODEX_SERVICE_URL", "")
            ),
            "mcp_base_url": get(SystemConfigService).get_value(
                "mcp_base_url", os.getenv("MCP_BASE_URL", "http://tdmcp:8001")
            ),
            "docgen_timeout": get(SystemConfigService).get_value(
                "docgen_timeout", int(os.getenv("DOCGEN_TIMEOUT", "1800"))
            ),
            "doclibgen_timeout": get(SystemConfigService).get_value(
                "doclibgen_timeout", int(os.getenv("DOCLIBGEN_TIMEOUT", "3600"))
            ),
            "chartgen_timeout": get(SystemConfigService).get_value(
                "chartgen_timeout", int(os.getenv("CHARTGEN_TIMEOUT", "1800"))
            ),
            "max_row_limit": get(SystemConfigService).get_value("max_row_limit", None),
            "hot_reload_interval": get(SystemConfigService).get_value(
                "hot_reload_interval",
                int(_hri) if (_hri := os.getenv("TETHERDUST_HOT_RELOAD_INTERVAL")) else None,
            ),
        }
        form = GeneralSettingsForm(initial=initial)

    return render(
        request,
        "management/sysconfig/general_settings.html",
        {
            "form": form,
            "section": "settings",
        },
    )
