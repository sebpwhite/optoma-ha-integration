"""Serial client for Optoma projectors."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import logging

import serialx

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .const import OPTOMA_BAUDRATE

_LOGGER = logging.getLogger(__name__)

POWER_ON = b"~0000 1\r"
POWER_OFF = b"~0000 0\r"
QUERY_POWER = b"~00124 1\r"

POWER_QUERY_TIMEOUT = 3.0


class OptomaProjector:
    """Control an Optoma projector over a serialx serial connection."""

    def __init__(self, port: str) -> None:
        """Initialize the projector client."""
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._connected = False
        self._power: bool | None = None
        self._buffer = bytearray()
        self._info_scan = b""
        self._listeners: list[Callable[[], None]] = []
        self._pending_power_queries: list[asyncio.Future[bool]] = []
        self._command_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        """Return if the serial connection is open."""
        return self._connected

    @property
    def power(self) -> bool | None:
        """Return the last known projector power state."""
        return self._power

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
            await self.async_query_power()

    async def async_disconnect(self) -> None:
        """Close the serial connection."""
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
        self._notify_listeners()

    async def async_query_power(self) -> bool:
        """Query and return the projector power state."""
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending_power_queries.append(future)

        try:
            async with self._command_lock:
                await self._write(QUERY_POWER)
            return await asyncio.wait_for(future, POWER_QUERY_TIMEOUT)
        finally:
            if future in self._pending_power_queries:
                self._pending_power_queries.remove(future)

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
        self._schedule_delayed_power_query()

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
        for idx in range(max(0, len(scan) - 4)):
            if scan[idx : idx + 4] != b"INFO":
                continue
            status = scan[idx + 4 : idx + 5]
            if status in (b"0", b"1", b"2"):
                self._set_power(status == b"1")
        self._info_scan = scan[-4:]

    def _handle_frame(self, frame: bytes) -> None:
        """Parse a single CR-terminated Optoma response."""
        if not frame:
            return

        if b"INFO" in frame:
            self._scan_info_notifications(frame)
            return

        power = self._parse_power_query_response(frame)
        if power is not None:
            self._set_power(power)
            self._resolve_pending_power_queries(power)
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

    def _set_power(self, power: bool) -> None:
        """Set power state and notify listeners."""
        if self._power == power:
            return
        self._power = power
        self._notify_listeners()

    def _resolve_pending_power_queries(self, power: bool) -> None:
        """Resolve pending power query futures."""
        pending = list(self._pending_power_queries)
        self._pending_power_queries.clear()
        for future in pending:
            if not future.done():
                future.set_result(power)

    def _fail_pending_power_queries(self) -> None:
        """Fail pending power query futures after disconnect."""
        pending = list(self._pending_power_queries)
        self._pending_power_queries.clear()
        for future in pending:
            if not future.done():
                future.set_exception(HomeAssistantError("Serial port disconnected"))

    def _schedule_delayed_power_query(self) -> None:
        """Schedule a delayed state refresh after a power command."""
        async def _query_later() -> None:
            await asyncio.sleep(15)
            if self._connected:
                with contextlib.suppress(HomeAssistantError, TimeoutError, OSError):
                    await self.async_query_power()

        asyncio.create_task(_query_later())

    def _notify_listeners(self) -> None:
        """Notify Home Assistant entities that state changed."""
        for listener in list(self._listeners):
            listener()
