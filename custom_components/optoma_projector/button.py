"""Button platform for the Optoma Projector integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .projector import OptomaProjector


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Optoma Projector buttons."""
    projector = config_entry.runtime_data
    async_add_entities(
        [
            OptomaProjectorButton(
                projector,
                config_entry,
                "resync",
                "Re-sync",
                projector.async_resync,
            )
        ]
    )


class OptomaProjectorButton(ButtonEntity):
    """Representation of an Optoma projector button."""

    _attr_has_entity_name = True

    def __init__(
        self,
        projector: OptomaProjector,
        config_entry: ConfigEntry,
        key: str,
        name: str,
        press_fn: Callable[[], Awaitable[None]],
    ) -> None:
        """Initialize the button."""
        self._projector = projector
        self._press_fn = press_fn
        self._attr_name = name
        self._attr_unique_id = f"{config_entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "manufacturer": "Optoma",
            "name": config_entry.title,
        }

    @property
    def available(self) -> bool:
        """Return if the projector transport is available."""
        return self._projector.connected and self._projector.power is not False

    async def async_press(self) -> None:
        """Press the button."""
        await self._press_fn()
