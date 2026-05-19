"""Switch platform for the Optoma Projector integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.switch import SwitchEntity
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
    """Set up Optoma Projector switches."""
    projector = config_entry.runtime_data
    async_add_entities(
        [
            OptomaProjectorSwitch(
                projector,
                config_entry,
                "av_mute",
                "AV Mute",
                lambda projector: projector.av_mute,
                projector.async_set_av_mute,
                projector.async_query_av_mute,
            ),
            OptomaProjectorSwitch(
                projector,
                config_entry,
                "freeze",
                "Freeze",
                lambda projector: projector.freeze,
                projector.async_set_freeze,
                None,
            ),
            OptomaProjectorSwitch(
                projector,
                config_entry,
                "3d_mode",
                "3D Mode",
                lambda projector: projector.three_d_mode,
                projector.async_set_three_d_mode,
                projector.async_query_three_d_mode,
            ),
            OptomaProjectorSwitch(
                projector,
                config_entry,
                "3d_sync_invert",
                "3D Sync Invert",
                lambda projector: projector.three_d_sync_invert,
                projector.async_set_three_d_sync_invert,
                None,
            ),
        ]
    )


class OptomaProjectorSwitch(SwitchEntity):
    """Representation of an Optoma projector switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        projector: OptomaProjector,
        config_entry: ConfigEntry,
        key: str,
        name: str,
        value_fn: Callable[[OptomaProjector], bool | None],
        set_fn: Callable[[bool], Awaitable[None]],
        update_fn: Callable[[], Awaitable[bool]] | None,
    ) -> None:
        """Initialize the switch."""
        self._projector = projector
        self._value_fn = value_fn
        self._set_fn = set_fn
        self._update_fn = update_fn
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

    @property
    def is_on(self) -> bool | None:
        """Return the current switch state."""
        return self._value_fn(self._projector)

    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn on the switch."""
        await self._set_fn(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn off the switch."""
        await self._set_fn(False)

    async def async_added_to_hass(self) -> None:
        """Subscribe to projector state updates."""
        self.async_on_remove(self._projector.subscribe(self._async_on_state_update))

    async def async_update(self) -> None:
        """Update the switch state."""
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
