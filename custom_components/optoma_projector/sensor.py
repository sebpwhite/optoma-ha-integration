"""Sensor platform for the Optoma Projector integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .projector import OptomaProjector


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Optoma Projector sensors."""
    projector = config_entry.runtime_data
    async_add_entities(
        [
            OptomaProjectorSensor(
                projector,
                config_entry,
                "status",
                "Status",
                lambda projector: projector.status,
                None,
                None,
            ),
            OptomaProjectorSensor(
                projector,
                config_entry,
                "lamp_hours",
                "Lamp Hours",
                lambda projector: projector.lamp_hours,
                projector.async_query_lamp_hours,
                UnitOfTime.HOURS,
            ),
            OptomaProjectorSensor(
                projector,
                config_entry,
                "temperature",
                "Temperature",
                lambda projector: projector.temperature,
                projector.async_query_temperature,
                UnitOfTemperature.CELSIUS,
                SensorDeviceClass.TEMPERATURE,
                True,
            ),
        ]
    )


class OptomaProjectorSensor(SensorEntity):
    """Representation of an Optoma projector sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        projector: OptomaProjector,
        config_entry: ConfigEntry,
        key: str,
        name: str,
        value_fn: Callable[[OptomaProjector], str | int | None],
        update_fn: Callable[[], Awaitable[object]] | None,
        unit: str | None,
        device_class: SensorDeviceClass | None = None,
        requires_power: bool = False,
    ) -> None:
        """Initialize the sensor."""
        self._projector = projector
        self._value_fn = value_fn
        self._update_fn = update_fn
        self._requires_power = requires_power
        self._attr_name = name
        self._attr_unique_id = f"{config_entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "manufacturer": "Optoma",
            "name": config_entry.title,
        }

    @property
    def available(self) -> bool:
        """Return if the projector transport is available."""
        return self._projector.connected and (
            not self._requires_power or self._projector.power is not False
        )

    @property
    def native_value(self) -> str | int | None:
        """Return the current sensor state."""
        return self._value_fn(self._projector)

    async def async_added_to_hass(self) -> None:
        """Subscribe to projector state updates."""
        self.async_on_remove(self._projector.subscribe(self._async_on_state_update))

    async def async_update(self) -> None:
        """Update the sensor state."""
        if (
            self._update_fn is not None
            and self._projector.connected
            and (not self._requires_power or self._projector.power is not False)
        ):
            await self._update_fn()

    @callback
    def _async_on_state_update(self) -> None:
        """Handle a projector state update."""
        self.async_write_ha_state()
