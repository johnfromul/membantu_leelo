"""
Membantu LeeLo01/02 BLE driver.

PROTOCOL (fully reverse-engineered via Frida):
- c304 = WRITE characteristic (commands to device)
- c306 = INDICATE characteristic (responses/echo from device)

Packet format: AA [CMD] [LEN] [DATA...] DD 0D 0A

Commands (CONFIRMED semantics):
- CMD 0x01 = handshake (value 0x01 on connect)
- CMD 0x02 = SPEED, value 0x00-0x0A (0-10)
- CMD 0x03 = TIMER INTERVAL selection:
      0x00 = 15 min
      0x01 = 30 min
      0x02 = 45 min
      0x03 = 60 min
      0x04 = Unlimited (no time limit)
- CMD 0x04 = ON/OFF (start/stop swinging):
      0x00 = START
      0x01 = STOP
- CMD 0x07 = SYNC/STATUS (device reports state, 5 bytes)
- CMD 0x0A = ACK/wake

To start swinging:  set interval (0x03), set speed (0x02), then START (0x04 00)
To stop swinging:   STOP (0x04 01)
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import time

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

_LOGGER = logging.getLogger(__name__)

CHAR_WRITE_UUID    = "0000c304-0000-1000-8000-00805f9b34fb"
CHAR_INDICATE_UUID = "0000c306-0000-1000-8000-00805f9b34fb"

START_BYTE = 0xAA
END_BYTES  = bytes([0xDD, 0x0D, 0x0A])

CMD_HANDSHAKE = 0x01
CMD_SPEED     = 0x02
CMD_INTERVAL  = 0x03   # timer interval selection
CMD_ONOFF     = 0x04   # start/stop
CMD_SYNC      = 0x07
CMD_ACK       = 0x0A

ONOFF_START = 0x00
ONOFF_STOP  = 0x01

# Timer interval -> CMD_INTERVAL byte
INTERVAL_BYTES = {
    "15 min":    0x00,
    "30 min":    0x01,
    "45 min":    0x02,
    "60 min":    0x03,
    "Unlimited": 0x04,
}

# Timer interval -> minutes (None = unlimited)
INTERVAL_MINUTES = {
    "15 min":    15,
    "30 min":    30,
    "45 min":    45,
    "60 min":    60,
    "Unlimited": None,
}


def build_cmd(cmd: int, data: list[int]) -> bytes:
    payload = [START_BYTE, cmd, len(data)] + data
    return bytes(payload) + END_BYTES


def _bluetoothctl_remove(address: str) -> None:
    """Disconnect and remove device from BlueZ cache for a clean connect."""
    for action in ("disconnect", "remove"):
        try:
            subprocess.run(
                ["bluetoothctl", "--", action, address],
                timeout=5,
                capture_output=True,
            )
        except Exception as e:
            _LOGGER.debug("bluetoothctl %s failed: %s", action, e)
    _LOGGER.debug("BlueZ cache cleared for %s", address)


class LeeLoDevice:
    def __init__(self, ble_device: BLEDevice, initial_speed: int = 5, initial_timer: str = "Unlimited"):
        self._ble_device = ble_device
        self._client: BleakClient | None = None
        self._speed = max(1, min(10, initial_speed))
        self._timer = initial_timer
        self._running = False
        self._start_time: float | None = None

    @property
    def address(self) -> str:
        return self._ble_device.address

    async def connect(self) -> bool:
        _bluetoothctl_remove(self.address)
        await asyncio.sleep(1.0)
        try:
            self._client = await establish_connection(
                BleakClient,
                self._ble_device,
                self._ble_device.address,
                disconnected_callback=self._on_disconnect,
            )
            _LOGGER.info("Connected to LeeLo %s", self.address)
            # Verify service discovery completed — write char must exist
            char = self._client.services.get_characteristic(CHAR_WRITE_UUID)
            if char is None:
                _LOGGER.warning("Write characteristic not found — incomplete discovery, disconnecting")
                await self._client.disconnect()
                self._client = None
                return False
            try:
                await self._client.start_notify(CHAR_INDICATE_UUID, self._on_indicate)
                _LOGGER.info("Indicate notifications enabled")
            except Exception as e:
                _LOGGER.debug("Indicate not available: %s", e)
            await self._init_sequence()
            return True
        except Exception as e:
            _LOGGER.error("Connection failed for %s: %s", self.address, e)
            return False

    async def _init_sequence(self) -> None:
        """Handshake + ack. Does NOT start swinging."""
        _LOGGER.info("Sending init sequence")
        await self._write(CMD_HANDSHAKE, [0x01])
        await asyncio.sleep(0.15)
        await self._write(CMD_ACK, [0x00])
        self._running = False
        _LOGGER.info("Init sequence complete")

    def _on_disconnect(self, client: BleakClient) -> None:
        _LOGGER.warning("LeeLo disconnected")
        self._running = False

    def _on_indicate(self, sender: int, data: bytearray) -> None:
        _LOGGER.debug("Indicate: %s", data.hex())
        # Parse CMD 0x04 on/off state: AA 04 01 xx
        i = 0
        while i < len(data) - 3:
            if data[i] == 0xAA and data[i+1] == 0x04 and data[i+2] == 0x01:
                # 0x00 = started, 0x01 = stopped
                self._running = (data[i+3] == 0x00)
                break
            i += 1

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected:
            await self._client.disconnect()

    async def _write(self, cmd: int, data: list[int]) -> bool:
        if not self._client or not self._client.is_connected:
            _LOGGER.warning("LeeLo not connected")
            return False
        packet = build_cmd(cmd, data)
        _LOGGER.info("BLE write: %s", packet.hex())
        await self._client.write_gatt_char(CHAR_WRITE_UUID, packet)
        return True

    async def start(self) -> None:
        """Start swinging: set interval + speed, then START."""
        interval_byte = INTERVAL_BYTES.get(self._timer, 0x04)
        await self._write(CMD_INTERVAL, [interval_byte])
        await asyncio.sleep(0.1)
        await self._write(CMD_SPEED, [self._speed])
        await asyncio.sleep(0.1)
        ok = await self._write(CMD_ONOFF, [ONOFF_START])
        if ok:
            self._running = True
            self._start_time = time.monotonic()

    async def stop(self) -> None:
        """Stop swinging."""
        ok = await self._write(CMD_ONOFF, [ONOFF_STOP])
        if ok:
            self._running = False
            self._start_time = None

    def set_speed_local(self, speed: int) -> None:
        self._speed = max(1, min(10, speed))

    def set_timer_local(self, timer: str) -> None:
        self._timer = timer

    async def apply_speed(self, speed: int) -> None:
        """Write speed to device immediately (live change)."""
        self._speed = max(1, min(10, speed))
        await self._write(CMD_SPEED, [self._speed])

    async def apply_timer(self, timer: str) -> None:
        """Write interval to device immediately (live change)."""
        self._timer = timer
        interval_byte = INTERVAL_BYTES.get(timer, 0x04)
        await self._write(CMD_INTERVAL, [interval_byte])
        # Reset countdown when interval changes while running
        if self._running:
            self._start_time = time.monotonic()

    def remaining_seconds(self) -> int | None:
        """Return remaining seconds, or None if unlimited/not running.
        Auto-clears running state when countdown reaches zero (timer expired).
        """
        if not self._running or self._start_time is None:
            return None
        minutes = INTERVAL_MINUTES.get(self._timer)
        if minutes is None:
            return None
        elapsed = time.monotonic() - self._start_time
        remaining = int(minutes * 60 - elapsed)
        if remaining <= 0:
            # Timer expired — device has auto-stopped
            self._running = False
            self._start_time = None
            return 0
        return remaining

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def speed(self) -> int:
        return self._speed

    @property
    def timer(self) -> str:
        return self._timer

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected