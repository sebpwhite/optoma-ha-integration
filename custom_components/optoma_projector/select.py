"""Select platform for the Optoma Projector integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .projector import (
    ASPECT_RATIO_OPTIONS,
    BRIGHTNESS_MODE_OPTIONS,
    DISPLAY_MODE_OPTIONS,
    THREE_D_FORMAT_OPTIONS,
    OptomaProjector,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Optoma Projector selects."""
    projector = config_entry.runtime_data
    async_add_entities(
        [
            OptomaProjectorSelect(
                projector,
                config_entry,
                "display_mode",
                "Display Mode",
                list(DISPLAY_MODE_OPTIONS),
                lambda projector: projector.display_mode,
                projector.async_set_display_mode,
                projector.async_query_display_mode,
            ),
            OptomaProjectorSelect(
                projector,
                config_entry,
                "aspect_ratio",
                "Aspect Ratio",
                list(ASPECT_RATIO_OPTIONS),
                lambda projector: projector.aspect_ratio,
                projector.async_set_aspect_ratio,
                projector.async_query_aspect_ratio,
            ),
            OptomaProjectorSelect(
                projector,
                config_entry,
                "brightness_mode",
                "Brightness Mode",
                list(BRIGHTNESS_MODE_OPTIONS),
                lambda projector: projector.brightness_mode,
                projector.async_set_brightness_mode,
                None,
            ),
            OptomaProjectorSelect(
                projector,
                config_entry,
                "3d_format",
                "3D Format",
                list(THREE_D_FORMAT_OPTIONS),
                lambda projector: projector.three_d_format,
                projector.async_set_three_d_format,
                None,
            ),
        ]
    )


class OptomaProjectorSelect(SelectEntity):
    """Representation of an Optoma projector select."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        projector: OptomaProjector,
        config_entry: ConfigEntry,
        key: str,
        name: str,
        options: list[str],
        value_fn: Callable[[OptomaProjector], str | None],
        set_fn: Callable[[str], Awaitable[None]],
        update_fn: Callable[[], Awaitable[str]] | None,
    ) -> None:
        """Initialize the select."""
        self._projector = projector
        self._value_fn = value_fn
        self._set_fn = set_fn
        self._update_fn = update_fn
        self._attr_name = name
        self._attr_unique_id = f"{config_entry.entry_id}_{key}"
        self._attr_options = options
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "manufacturer": "Optoma",
            "name": config_entry.title,
        }

    @property
    def available(self) -> bool:
        """Return if the projector transport is available."""
        return self._projector.connected and self._projector.power is not False

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self._value_fn(self._projector)

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        await self._set_fn(option)

    async def async_added_to_hass(self) -> None:
        """Subscribe to projector state updates."""
        self.async_on_remove(self._projector.subscribe(self._async_on_state_update))

    async def async_update(self) -> None:
        """Update the select state."""
        if (
            self._update_fn is not None
            and self._projector.connected
            and self._projector.power is not False
        ):
            await self._update_fn()

    @callback
    def _async_on_state_update(self) -> None:
        """Handle a projector state update."""
        self.async_write_ha_state()
