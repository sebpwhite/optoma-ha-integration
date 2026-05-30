"""Serial client for Optoma projectors."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
from dataclasses import dataclass
import logging

import serialx

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .const import OPTOMA_BAUDRATE

_LOGGER = logging.getLogger(__name__)

POWER_QUERY_TIMEOUT = 3.0
INPUT_QUERY_TIMEOUT = 3.0
GENERIC_QUERY_TIMEOUT = 3.0
POWER_POLL_INTERVAL = 15.0
INPUT_POLL_EVERY_N_POWER_POLLS = 4


def _command(command: int, value: int | str) -> bytes:
    """Build an Optoma ASCII command for projector ID 00."""
    return f"~00{command:02d} {value}\r".encode()


POWER_ON = _command(0, 1)
POWER_OFF = _command(0, 0)
QUERY_POWER = _command(124, 1)
QUERY_INPUT = _command(121, 1)

SOURCE_HDMI_1_MHL = "HDMI 1/MHL"
SOURCE_HDMI_2 = "HDMI 2"
SOURCE_VGA = "VGA"
SOURCE_LIST = [SOURCE_HDMI_1_MHL, SOURCE_HDMI_2, SOURCE_VGA]
SOURCE_TO_COMMAND = {
    SOURCE_HDMI_1_MHL: _command(12, 1),
    SOURCE_HDMI_2: _command(12, 15),
    SOURCE_VGA: _command(12, 5),
}
INPUT_RESPONSE_TO_SOURCE = {
    b"1": SOURCE_VGA,
    b"7": SOURCE_HDMI_1_MHL,
    b"8": SOURCE_HDMI_2,
    b"9": SOURCE_VGA,
}

INFO_STATUS = {
    0: "Standby",
    1: "Warming up",
    2: "Cooling down",
    3: "Out of range",
    4: "Lamp fail",
    5: "Thermal switch error",
    6: "Fan lock",
    7: "Over temperature",
    8: "Lamp hours running out",
    9: "Cover open",
    10: "Lamp ignite fail",
    11: "Format board power on fail",
    12: "Color wheel unexpected stop",
    13: "Over temperature",
    14: "Fan 1 lock",
    15: "Fan 2 lock",
    16: "Fan 3 lock",
    17: "Fan 4 lock",
    18: "Fan 5 lock",
    19: "LAN fail then restart",
    20: "Light source lower than 60%",
    21: "Light source NTC 1 over temperature",
    22: "Light source NTC 2 over temperature",
    23: "High ambient temperature",
    24: "System ready",
}

DISPLAY_MODE_OPTIONS = {
    "Presentation": 1,
    "Bright": 2,
    "Cinema": 3,
    "HDR": 21,
    "sRGB": 4,
    "User": 5,
    "3D": 9,
}
DISPLAY_MODE_RESPONSE = {
    b"1": "Presentation",
    b"2": "Bright",
    b"3": "Cinema",
    b"21": "HDR",
    b"4": "sRGB",
    b"5": "User",
    b"9": "3D",
}

ASPECT_RATIO_OPTIONS = {
    "4:3": 1,
    "16:9": 2,
    "LBX": 5,
    "Native": 6,
    "Auto": 7,
}
ASPECT_RATIO_RESPONSE = {
    str(value).encode(): name for name, value in ASPECT_RATIO_OPTIONS.items()
}

BRIGHTNESS_MODE_OPTIONS = {
    "Bright": 1,
    "Eco": 3,
    "Dynamic": 4,
}

THREE_D_FORMAT_OPTIONS = {
    "Auto": 0,
    "Frame Packing": 7,
    "Side by Side": 1,
    "Top and Bottom": 2,
    "Frame Sequential": 3,
}


@dataclass(slots=True)
class _PendingPayloadQuery:
    """Pending generic command response."""

    future: asyncio.Future[bytes]


class OptomaProjector:
    """Control an Optoma projector over a serialx serial connection."""

    def __init__(self, port: str) -> None:
        """Initialize the projector client."""
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._connected = False
        self._power: bool | None = None
        self._source: str | None = None
        self._status_code: int | None = None
        self._status: str | None = None
        self._lamp_hours: int | None = None
        self._temperature: int | None = None
        self._av_mute: bool | None = None
        self._freeze: bool | None = None
        self._three_d_mode: bool | None = None
        self._three_d_sync_invert: bool | None = None
        self._display_mode: str | None = None
        self._aspect_ratio: str | None = None
        self._brightness_mode: str | None = None
        self._three_d_format: str | None = None
        self._brightness: int | None = None
        self._contrast: int | None = None
        self._vertical_keystone: int | None = None
        self._buffer = bytearray()
        self._info_scan = b""
        self._listeners: list[Callable[[], None]] = []
        self._pending_power_queries: list[asyncio.Future[bool]] = []
        self._pending_input_queries: list[asyncio.Future[str]] = []
        self._pending_payload_queries: list[_PendingPayloadQuery] = []
        self._command_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        """Return if the serial connection is open."""
        return self._connected

    @property
    def power(self) -> bool | None:
        """Return the last known projector power state."""
        return self._power

    @property
    def source(self) -> str | None:
        """Return the last known projector input source."""
        return self._source

    @property
    def status(self) -> str | None:
        """Return the last projector status message."""
        return self._status

    @property
    def status_code(self) -> int | None:
        """Return the last projector status code."""
        return self._status_code

    @property
    def lamp_hours(self) -> int | None:
        """Return the last known lamp hours."""
        return self._lamp_hours

    @property
    def temperature(self) -> int | None:
        """Return the last known projector temperature."""
        return self._temperature

    @property
    def av_mute(self) -> bool | None:
        """Return the last known AV mute state."""
        return self._av_mute

    @property
    def freeze(self) -> bool | None:
        """Return the last known freeze state."""
        return self._freeze

    @property
    def three_d_mode(self) -> bool | None:
        """Return the last known 3D mode state."""
        return self._three_d_mode

    @property
    def three_d_sync_invert(self) -> bool | None:
        """Return the last known 3D sync invert state."""
        return self._three_d_sync_invert

    @property
    def display_mode(self) -> str | None:
        """Return the last known display mode."""
        return self._display_mode

    @property
    def aspect_ratio(self) -> str | None:
        """Return the last known aspect ratio."""
        return self._aspect_ratio

    @property
    def brightness_mode(self) -> str | None:
        """Return the last known brightness mode."""
        return self._brightness_mode

    @property
    def three_d_format(self) -> str | None:
        """Return the last known 3D format."""
        return self._three_d_format

    @property
    def brightness(self) -> int | None:
        """Return the last known brightness setting."""
        return self._brightness

    @property
    def contrast(self) -> int | None:
        """Return the last known contrast setting."""
        return self._contrast

    @property
    def vertical_keystone(self) -> int | None:
        """Return the last known vertical keystone setting."""
        return self._vertical_keystone

    async def async_connect(self, *, query_power: bool = True) -> None:
        """Open the serial connection."""
        self._reader, self._writer = await serialx.open_serial_connection(
            url=self._port,
            baudrate=OPTOMA_BAUDRATE,
        )
        self._connected = True
        self._reader_task = asyncio.create_task(self._read_loop())
        self._notify_listeners()

        if query_power:
            power = await self.async_query_power()
            if power:
                with contextlib.suppress(HomeAssistantError, TimeoutError, OSError):
                    await self.async_query_input()
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def async_disconnect(self) -> None:
        """Close the serial connection."""
        poll_task = self._poll_task
        if poll_task is not None:
            poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poll_task
            self._poll_task = None

        reader_task = self._reader_task
        if reader_task is not None:
            reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader_task
            self._reader_task = None

        writer = self._writer
        if writer is not None:
            writer.close()
            with contextlib.suppress(AttributeError, OSError):
                await writer.wait_closed()

        self._reader = None
        self._writer = None
        self._connected = False
        self._fail_pending_power_queries()
        self._fail_pending_input_queries()
        self._fail_pending_payload_queries()
        self._notify_listeners()

    async def _poll_loop(self) -> None:
        """Poll projector state so external controls do not desync HA state."""
        poll_count = 0
        while self._connected:
            await asyncio.sleep(POWER_POLL_INTERVAL)
            poll_count += 1
            previous_power = self._power

            try:
                power = await self.async_query_power()
            except (HomeAssistantError, TimeoutError, OSError):
                _LOGGER.debug("Power poll failed", exc_info=True)
                continue

            if not power:
                continue

            if (
                previous_power is not True
                or poll_count % INPUT_POLL_EVERY_N_POWER_POLLS == 0
            ):
                with contextlib.suppress(HomeAssistantError, TimeoutError, OSError):
                    await self.async_query_input()

    async def async_query_power(self) -> bool:
        """Query and return the projector power state."""
        async with self._command_lock:
            future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
            self._pending_power_queries.append(future)
            try:
                await self._write(QUERY_POWER)
                return await asyncio.wait_for(future, POWER_QUERY_TIMEOUT)
            finally:
                if future in self._pending_power_queries:
                    self._pending_power_queries.remove(future)

    async def async_query_input(self) -> str:
        """Query and return the projector input source."""
        async with self._command_lock:
            future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            self._pending_input_queries.append(future)
            try:
                await self._write(QUERY_INPUT)
                return await asyncio.wait_for(future, INPUT_QUERY_TIMEOUT)
            finally:
                if future in self._pending_input_queries:
                    self._pending_input_queries.remove(future)

    async def async_query_lamp_hours(self) -> int:
        """Query and return lamp hours."""
        value = self._parse_int_payload(await self._query_payload(108, 1))
        self._set_attr("_lamp_hours", value)
        return value

    async def async_query_temperature(self) -> int:
        """Query and return system temperature."""
        value = self._parse_int_payload(await self._query_payload(150, 18))
        self._set_attr("_temperature", value)
        return value

    async def async_query_av_mute(self) -> bool:
        """Query and return AV mute state."""
        value = self._parse_bool_payload(await self._query_payload(355, 1))
        self._set_attr("_av_mute", value)
        return value

    async def async_set_av_mute(self, enabled: bool) -> None:
        """Set AV mute state."""
        await self._write_command(2, int(enabled))
        self._set_attr("_av_mute", enabled)

    async def async_set_freeze(self, enabled: bool) -> None:
        """Set freeze state."""
        await self._write_command(4, int(enabled))
        self._set_attr("_freeze", enabled)

    async def async_query_three_d_mode(self) -> bool:
        """Query and return 3D mode state."""
        value = self._parse_bool_payload(await self._query_payload(130, 1))
        self._set_attr("_three_d_mode", value)
        return value

    async def async_set_three_d_mode(self, enabled: bool) -> None:
        """Set 3D mode state."""
        await self._write_command(230, 4 if enabled else 0)
        self._set_attr("_three_d_mode", enabled)

    async def async_set_three_d_sync_invert(self, enabled: bool) -> None:
        """Set 3D sync invert state."""
        await self._write_command(231, int(enabled))
        self._set_attr("_three_d_sync_invert", enabled)

    async def async_query_display_mode(self) -> str:
        """Query and return display mode."""
        value = self._map_payload(
            await self._query_payload(123, 1), DISPLAY_MODE_RESPONSE
        )
        self._set_attr("_display_mode", value)
        return value

    async def async_set_display_mode(self, mode: str) -> None:
        """Set display mode."""
        await self._write_command(20, DISPLAY_MODE_OPTIONS[mode])
        self._set_attr("_display_mode", mode)

    async def async_query_aspect_ratio(self) -> str:
        """Query and return aspect ratio."""
        value = self._map_payload(
            await self._query_payload(127, 1), ASPECT_RATIO_RESPONSE
        )
        self._set_attr("_aspect_ratio", value)
        return value

    async def async_set_aspect_ratio(self, aspect_ratio: str) -> None:
        """Set aspect ratio."""
        await self._write_command(60, ASPECT_RATIO_OPTIONS[aspect_ratio])
        self._set_attr("_aspect_ratio", aspect_ratio)

    async def async_set_brightness_mode(self, mode: str) -> None:
        """Set brightness mode."""
        await self._write_command(110, BRIGHTNESS_MODE_OPTIONS[mode])
        self._set_attr("_brightness_mode", mode)

    async def async_set_three_d_format(self, format_name: str) -> None:
        """Set 3D format."""
        await self._write_command(405, THREE_D_FORMAT_OPTIONS[format_name])
        self._set_attr("_three_d_format", format_name)

    async def async_query_brightness(self) -> int:
        """Query and return brightness setting."""
        value = self._parse_int_payload(await self._query_payload(125, 1))
        self._set_attr("_brightness", value)
        return value

    async def async_set_brightness(self, value: int) -> None:
        """Set brightness setting."""
        await self._write_command(21, value)
        self._set_attr("_brightness", value)

    async def async_query_contrast(self) -> int:
        """Query and return contrast setting."""
        value = self._parse_int_payload(await self._query_payload(126, 1))
        self._set_attr("_contrast", value)
        return value

    async def async_set_contrast(self, value: int) -> None:
        """Set contrast setting."""
        await self._write_command(22, value)
        self._set_attr("_contrast", value)

    async def async_query_vertical_keystone(self) -> int:
        """Query and return vertical keystone setting."""
        value = self._parse_int_payload(await self._query_payload(543, 3))
        self._set_attr("_vertical_keystone", value)
        return value

    async def async_set_vertical_keystone(self, value: int) -> None:
        """Set vertical keystone setting."""
        await self._write_command(66, value)
        self._set_attr("_vertical_keystone", value)

    async def async_resync(self) -> None:
        """Send the re-sync command."""
        await self._write_command(1, 1)

    async def async_turn_on(self) -> None:
        """Turn the projector on."""
        async with self._command_lock:
            await self._write(POWER_ON)
        self._set_power(True)
        self._schedule_delayed_power_query()

    async def async_turn_off(self) -> None:
        """Turn the projector off."""
        async with self._command_lock:
            await self._write(POWER_OFF)
        self._set_power(False)
        self._set_source(None)
        self._schedule_delayed_power_query()

    async def async_select_source(self, source: str) -> None:
        """Select the projector input source."""
        command = SOURCE_TO_COMMAND.get(source)
        if command is None:
            raise HomeAssistantError(f"Unsupported projector source: {source}")

        async with self._command_lock:
            await self._write(command)
        self._set_source(source)
        self._schedule_delayed_input_query()

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to projector state changes."""
        self._listeners.append(listener)

        def _unsubscribe() -> None:
            self._listeners.remove(listener)

        return _unsubscribe

    async def _write(self, data: bytes) -> None:
        """Write raw bytes to the projector."""
        if self._writer is None or not self._connected:
            raise HomeAssistantError("Projector serial port is not connected")
        self._writer.write(data)
        await self._writer.drain()

    async def _write_command(self, command: int, value: int | str) -> None:
        """Write an Optoma command."""
        async with self._command_lock:
            await self._write(_command(command, value))

    async def _query_payload(self, command: int, value: int | str) -> bytes:
        """Query an Optoma command and return the response payload."""
        async with self._command_lock:
            future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
            pending = _PendingPayloadQuery(future)
            self._pending_payload_queries.append(pending)
            try:
                await self._write(_command(command, value))
                return await asyncio.wait_for(future, GENERIC_QUERY_TIMEOUT)
            finally:
                if pending in self._pending_payload_queries:
                    self._pending_payload_queries.remove(pending)

    async def _read_loop(self) -> None:
        """Read and parse serial data."""
        assert self._reader is not None

        try:
            while self._connected:
                data = await self._reader.read(64)
                if not data:
                    raise ConnectionError("Serial port closed")
                self._handle_bytes(data)
        except asyncio.CancelledError:
            raise
        except (ConnectionError, OSError, TimeoutError, ValueError):
            _LOGGER.debug("Optoma serial connection closed", exc_info=True)
        self._connected = False
        self._fail_pending_power_queries()
        self._fail_pending_input_queries()
        self._fail_pending_payload_queries()
        self._notify_listeners()

    @callback
    def _handle_bytes(self, data: bytes) -> None:
        """Handle bytes received from the projector."""
        self._scan_info_notifications(data)
        self._buffer.extend(data)

        while b"\r" in self._buffer:
            frame, _, remaining = self._buffer.partition(b"\r")
            self._buffer = bytearray(remaining)
            self._handle_frame(bytes(frame))

        if len(self._buffer) > 128:
            _LOGGER.debug(
                "Dropping oversized partial Optoma response: %r", self._buffer
            )
            self._buffer.clear()

    def _scan_info_notifications(self, data: bytes) -> None:
        """Scan stream data for unsolicited Optoma INFO power notifications."""
        scan = self._info_scan + data
        idx = 0
        while idx <= len(scan) - 5:
            if scan[idx : idx + 4] != b"INFO":
                idx += 1
                continue
            end = idx + 4
            while end < len(scan) and scan[end : end + 1].isdigit():
                end += 1
            if end > idx + 4:
                code = int(scan[idx + 4 : end])
                self._set_status_code(code)
                if code in (0, 1, 2):
                    self._set_power(code == 1)
                idx = end
                continue
            idx += 1
        self._info_scan = scan[-8:]

    def _handle_frame(self, frame: bytes) -> None:
        """Parse a single CR-terminated Optoma response."""
        if not frame:
            return

        if b"INFO" in frame:
            self._scan_info_notifications(frame)
            return

        if self._handle_pending_payload_query(frame):
            return

        power = self._parse_power_query_response(frame)
        if power is not None:
            self._set_power(power)
            self._resolve_pending_power_queries(power)
            return

        source = self._parse_input_query_response(frame)
        if source is not None:
            self._set_source(source)
            self._resolve_pending_input_queries(source)
            return

        _LOGGER.debug("Unhandled Optoma response frame: %r", frame)

    @staticmethod
    def _parse_power_query_response(frame: bytes) -> bool | None:
        """Parse the compact power query response used by Optoma projectors."""
        if len(frame) >= 3 and frame[2:3] in (b"0", b"1"):
            return frame[2:3] == b"1"
        if frame in (b"0", b"1"):
            return frame == b"1"
        return None

    @staticmethod
    def _parse_input_query_response(frame: bytes) -> str | None:
        """Parse the compact input query response used by Optoma projectors."""
        if len(frame) >= 3:
            return INPUT_RESPONSE_TO_SOURCE.get(frame[2:])
        return INPUT_RESPONSE_TO_SOURCE.get(frame)

    @staticmethod
    def _extract_payload(frame: bytes) -> bytes | None:
        """Extract a payload from an Optoma response frame."""
        normalized = frame.strip().replace(b" ", b"")
        if normalized in (b"", b"P"):
            return None
        if normalized == b"F":
            raise HomeAssistantError("Projector returned failure")
        if normalized[:2].lower() == b"ok":
            return normalized[2:]
        return normalized

    @staticmethod
    def _parse_int_payload(payload: bytes) -> int:
        """Parse an integer command payload."""
        digits = b"".join(bytes([byte]) for byte in payload if 48 <= byte <= 57)
        if not digits:
            raise HomeAssistantError(
                f"Projector returned non-numeric payload: {payload!r}"
            )
        return int(digits)

    @classmethod
    def _parse_bool_payload(cls, payload: bytes) -> bool:
        """Parse a boolean command payload."""
        value = cls._parse_int_payload(payload)
        if value not in (0, 1):
            raise HomeAssistantError(
                f"Projector returned non-boolean payload: {payload!r}"
            )
        return bool(value)

    @classmethod
    def _map_payload(cls, payload: bytes, mapping: dict[bytes, str]) -> str:
        """Map a command payload to a named option."""
        normalized = payload.strip()
        value = mapping.get(normalized)
        if value is None:
            raise HomeAssistantError(
                f"Projector returned unsupported payload: {payload!r}"
            )
        return value

    def _set_power(self, power: bool) -> None:
        """Set power state and notify listeners."""
        power_changed = self._power != power
        source_changed = not power and self._source is not None
        if not power_changed and not source_changed:
            return
        self._power = power
        if not power:
            self._source = None
        self._notify_listeners()

    def _set_source(self, source: str | None) -> None:
        """Set input source and notify listeners."""
        if self._source == source:
            return
        self._source = source
        self._notify_listeners()

    def _set_status_code(self, code: int) -> None:
        """Set status code and notify listeners."""
        status = INFO_STATUS.get(code, f"Unknown status {code}")
        if self._status_code == code and self._status == status:
            return
        self._status_code = code
        self._status = status
        self._notify_listeners()

    def _set_attr(self, attr: str, value: object) -> None:
        """Set a state attribute and notify listeners."""
        if getattr(self, attr) == value:
            return
        setattr(self, attr, value)
        self._notify_listeners()

    def _handle_pending_payload_query(self, frame: bytes) -> bool:
        """Resolve a pending generic payload query if one exists."""
        if not self._pending_payload_queries:
            return False

        try:
            payload = self._extract_payload(frame)
        except HomeAssistantError as err:
            pending = self._pending_payload_queries.pop(0)
            if not pending.future.done():
                pending.future.set_exception(err)
            return True

        if payload is None:
            return True

        pending = self._pending_payload_queries.pop(0)
        if not pending.future.done():
            pending.future.set_result(payload)
        return True

    def _resolve_pending_power_queries(self, power: bool) -> None:
        """Resolve pending power query futures."""
        pending = list(self._pending_power_queries)
        self._pending_power_queries.clear()
        for future in pending:
            if not future.done():
                future.set_result(power)

    def _resolve_pending_input_queries(self, source: str) -> None:
        """Resolve pending input query futures."""
        pending = list(self._pending_input_queries)
        self._pending_input_queries.clear()
        for future in pending:
            if not future.done():
                future.set_result(source)

    def _fail_pending_power_queries(self) -> None:
        """Fail pending power query futures after disconnect."""
        pending = list(self._pending_power_queries)
        self._pending_power_queries.clear()
        for future in pending:
            if not future.done():
                future.set_exception(HomeAssistantError("Serial port disconnected"))

    def _fail_pending_payload_queries(self) -> None:
        """Fail pending generic command query futures after disconnect."""
        pending = list(self._pending_payload_queries)
        self._pending_payload_queries.clear()
        for query in pending:
            if not query.future.done():
                query.future.set_exception(
                    HomeAssistantError("Serial port disconnected")
                )

    def _fail_pending_input_queries(self) -> None:
        """Fail pending input query futures after disconnect."""
        pending = list(self._pending_input_queries)
        self._pending_input_queries.clear()
        for future in pending:
            if not future.done():
                future.set_exception(HomeAssistantError("Serial port disconnected"))

    def _schedule_delayed_power_query(self) -> None:
        """Schedule a delayed state refresh after a power command."""
        async def _query_later() -> None:
            await asyncio.sleep(15)
            if self._connected:
                with contextlib.suppress(HomeAssistantError, TimeoutError, OSError):
                    power = await self.async_query_power()
                    if power:
                        await self.async_query_input()

        asyncio.create_task(_query_later())

    def _schedule_delayed_input_query(self) -> None:
        """Schedule a delayed source refresh after an input command."""
        async def _query_later() -> None:
            await asyncio.sleep(2)
            if self._connected and self._power:
                with contextlib.suppress(HomeAssistantError, TimeoutError, OSError):
                    await self.async_query_input()

        asyncio.create_task(_query_later())

    def _notify_listeners(self) -> None:
        """Notify Home Assistant entities that state changed."""
        for listener in list(self._listeners):
            listener()
