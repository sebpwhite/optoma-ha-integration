"""Constants for the Optoma Projector integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "optoma_projector"
PLATFORMS: Final = [Platform.MEDIA_PLAYER]

DEFAULT_NAME: Final = "Optoma Projector"
OPTOMA_BAUDRATE: Final = 9600
