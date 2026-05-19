"""Config flow for the Optoma Projector integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import SerialPortSelector

from .const import DEFAULT_NAME, DOMAIN
from .projector import OptomaProjector


async def _async_attempt_connect(port: str) -> str | None:
    """Attempt to open the selected serial port."""
    projector = OptomaProjector(port)

    try:
        await projector.async_connect(query_power=False)
    except (ConnectionError, HomeAssistantError, OSError, TimeoutError, ValueError):
        return "cannot_connect"
    except Exception:  # noqa: BLE001
        return "unknown"
    else:
        await projector.async_disconnect()
        return None


class OptomaProjectorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Optoma Projector."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match({CONF_DEVICE: user_input[CONF_DEVICE]})
            error = await _async_attempt_connect(user_input[CONF_DEVICE])
            if error is None:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                        vol.Required(CONF_DEVICE): SerialPortSelector(),
                    }
                ),
                user_input or {},
            ),
            errors=errors,
        )
