"""Number platform for the Optoma Projector integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .projector import OptomaProjector


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Optoma Projector numbers."""
    projector = config_entry.runtime_data
    async_add_entities(
        [
            OptomaProjectorNumber(
                projector,
                config_entry,
                "brightness",
                "Brightness",
                lambda projector: projector.brightness,
                projector.async_set_brightness,
                projector.async_query_brightness,
                0,
                100,
            ),
            OptomaProjectorNumber(
                projector,
                config_entry,
                "contrast",
                "Contrast",
                lambda projector: projector.contrast,
                projector.async_set_contrast,
                projector.async_query_contrast,
                0,
                100,
            ),
            OptomaProjectorNumber(
                projector,
                config_entry,
                "vertical_keystone",
                "Vertical Keystone",
                lambda projector: projector.vertical_keystone,
                projector.async_set_vertical_keystone,
                projector.async_query_vertical_keystone,
                0,
                40,
            ),
        ]
    )


class OptomaProjectorNumber(NumberEntity):
    """Representation of an Optoma projector number."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1

    def __init__(
        self,
        projector: OptomaProjector,
        config_entry: ConfigEntry,
        key: str,
        name: str,
        value_fn: Callable[[OptomaProjector], int | None],
        set_fn: Callable[[int], Awaitable[None]],
        update_fn: Callable[[], Awaitable[int]],
        minimum: int,
        maximum: int,
    ) -> None:
        """Initialize the number."""
        self._projector = projector
        self._value_fn = value_fn
        self._set_fn = set_fn
        self._update_fn = update_fn
        self._attr_name = name
        self._attr_unique_id = f"{config_entry.entry_id}_{key}"
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
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
    def native_value(self) -> int | None:
        """Return the current number value."""
        return self._value_fn(self._projector)

    async def async_set_native_value(self, value: float) -> None:
        """Set the number value."""
        await self._set_fn(round(value))

    async def async_added_to_hass(self) -> None:
        """Subscribe to projector state updates."""
        self.async_on_remove(self._projector.subscribe(self._async_on_state_update))

    async def async_update(self) -> None:
        """Update the number state."""
        if self._projector.connected and self._projector.power is not False:
            await self._update_fn()

    @callback
    def _async_on_state_update(self) -> None:
        """Handle a projector state update."""
        self.async_write_ha_state()
