"""System configuration service: typed key-value access."""

from __future__ import annotations

import json
from typing import Any

from ..models.connections import SystemConfiguration


class SystemConfigService:
    """Read/write typed values in the :class:`SystemConfiguration` store."""

    def get_value(self, key: str, default: Any = None) -> Any:
        """Get a configuration value, cast to its declared type."""
        try:
            config = SystemConfiguration.objects.get(key=key)
        except SystemConfiguration.DoesNotExist:
            return default
        if config.value_type == "integer":
            return int(config.value)
        if config.value_type == "boolean":
            return config.value.lower() in ("true", "1", "yes")
        if config.value_type == "json":
            return json.loads(config.value)
        return config.value

    def set_value(
        self, key: str, value: Any, value_type: str = "string", description: str = ""
    ) -> SystemConfiguration:
        """Set a configuration value, serialising it for its declared type."""
        if value_type == "json" and not isinstance(value, str):
            value = json.dumps(value)
        elif value_type == "boolean":
            value = "true" if value else "false"
        else:
            value = str(value)

        config, _ = SystemConfiguration.objects.update_or_create(
            key=key,
            defaults={"value": value, "value_type": value_type, "description": description},
        )
        return config
