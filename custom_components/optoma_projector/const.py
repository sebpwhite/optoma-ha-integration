"""Constants for the Optoma Projector integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "optoma_projector"
PLATFORMS: Final = [
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

DEFAULT_NAME: Final = "Optoma Projector"
OPTOMA_BAUDRATE: Final = 9600
