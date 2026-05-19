"""The Optoma Projector integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError

from .const import PLATFORMS
from .projector import OptomaProjector


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Optoma Projector from a config entry."""
    projector = OptomaProjector(entry.data[CONF_DEVICE])

    try:
        await projector.async_connect()
    except (
        ConnectionError,
        HomeAssistantError,
        OSError,
        TimeoutError,
        ValueError,
    ) as err:
        if projector.connected:
            await projector.async_disconnect()
        raise ConfigEntryNotReady from err

    entry.runtime_data = projector
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_disconnect()
    return unload_ok
