"""Media player platform for the Optoma Projector integration."""

from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .projector import SOURCE_LIST, OptomaProjector


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Optoma Projector media player."""
    async_add_entities(
        [OptomaProjectorMediaPlayer(config_entry.runtime_data, config_entry)]
    )


class OptomaProjectorMediaPlayer(MediaPlayerEntity):
    """Representation of an Optoma projector."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(
        self, projector: OptomaProjector, config_entry: ConfigEntry
    ) -> None:
        """Initialize the media player."""
        self._projector = projector
        self._attr_unique_id = config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            manufacturer="Optoma",
            name=config_entry.title,
        )
        self._attr_source_list = SOURCE_LIST

    async def async_added_to_hass(self) -> None:
        """Subscribe to projector state updates."""
        self.async_on_remove(self._projector.subscribe(self._async_on_state_update))

    @property
    def available(self) -> bool:
        """Return if the projector transport is available."""
        return self._projector.connected

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the projector power state."""
        if self._projector.power is None:
            return None
        return MediaPlayerState.ON if self._projector.power else MediaPlayerState.OFF

    @property
    def source(self) -> str | None:
        """Return the current projector input source."""
        return self._projector.source

    async def async_turn_on(self) -> None:
        """Turn the projector on."""
        await self._projector.async_turn_on()

    async def async_turn_off(self) -> None:
        """Turn the projector off."""
        await self._projector.async_turn_off()

    async def async_select_source(self, source: str) -> None:
        """Select the projector input source."""
        await self._projector.async_select_source(source)

    @callback
    def _async_on_state_update(self) -> None:
        """Handle a projector state update."""
        self.async_write_ha_state()
