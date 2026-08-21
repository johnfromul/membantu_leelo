"""Membantu LeeLo – Switch entity (on/off)."""
from __future__ import annotations
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_register_callback,
    async_last_service_info,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta

from .leelo_ble import LeeLoDevice

_LOGGER = logging.getLogger(__name__)
DOMAIN = "membantu_leelo"
STORAGE_KEY = "membantu_leelo_state"
STORAGE_VERSION = 1


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    saved = await store.async_load() or {}

    entities = []
    for d in hass.data.get(DOMAIN, []):
        address = d["address"]
        name = d.get("name", "LeeLo")
        last_speed = saved.get(address, {}).get("speed", 5)
        last_timer = saved.get(address, {}).get("timer", "Unlimited")
        entities.append(LeeLoSwitch(hass, address, name, store, last_speed, last_timer))
    async_add_entities(entities, update_before_add=False)


class LeeLoSwitch(SwitchEntity):
    _attr_icon = "mdi:cradle"

    def __init__(self, hass, address, name, store, initial_speed, initial_timer):
        self._hass = hass
        self._address = address
        self._store = store
        self._initial_speed = initial_speed
        self._initial_timer = initial_timer
        self._device: LeeLoDevice | None = None
        self._attr_name = name
        self._attr_unique_id = f"leelo_switch_{address.replace(':', '')}"
        self._cancel_callback = None
        self._running_override = False
        self._cancel_timer = None

    async def async_added_to_hass(self) -> None:
        _LOGGER.info("LeeLo: looking for BLE device %s", self._address)
        service_info = async_last_service_info(self._hass, self._address, connectable=True)
        if service_info:
            await self._do_connect(service_info.device)
            return

        def _on_advertisement(service_info: BluetoothServiceInfoBleak, change: BluetoothChange) -> None:
            if self._device is not None and self._device.is_connected:
                return
            self._hass.async_create_task(self._do_connect(service_info.device))

        self._cancel_callback = async_register_callback(
            self._hass,
            _on_advertisement,
            {"address": self._address, "connectable": True},
            BluetoothScanningMode.ACTIVE,
        )

        # Periodic reconnect check every 60s
        async def _periodic_check(now):
            if self._device is None or not self._device.is_connected:
                info = async_last_service_info(self._hass, self._address, connectable=True)
                if info:
                    _LOGGER.debug("Periodic reconnect for LeeLo")
                    await self._do_connect(info.device)
            else:
                # Sync state — timer may have auto-stopped the device
                self._device.remaining_seconds()
                if self._running_override != self._device.is_running:
                    self._running_override = self._device.is_running
                    self.async_write_ha_state()

        self._cancel_timer = async_track_time_interval(
            self._hass, _periodic_check, timedelta(seconds=15)
        )

    async def _do_connect(self, ble_device) -> None:
        if self._cancel_callback:
            self._cancel_callback()
            self._cancel_callback = None
        self._running_override = False
        self._device = LeeLoDevice(self._hass, ble_device, self._initial_speed, self._initial_timer)
        result = await self._device.connect()
        _LOGGER.info("LeeLo connect result: %s", result)
        self._hass.data.setdefault("membantu_leelo_devices", {})[self._address] = self._device
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._cancel_callback:
            self._cancel_callback()
        if self._cancel_timer:
            self._cancel_timer()
        if self._device:
            await self._device.disconnect()

    @property
    def available(self) -> bool:
        return self._device is not None and self._device.is_connected

    @property
    def is_on(self) -> bool:
        # Reflect actual device state — timer may have auto-stopped it
        if self._device is not None and self._device.is_connected:
            # remaining_seconds() updates running state on expiry
            self._device.remaining_seconds()
            return self._device.is_running
        return self._running_override

    async def _ensure_connected(self) -> bool:
        """Reconnect if needed before an action."""
        if self._device is not None and self._device.is_connected:
            return True
        _LOGGER.info("LeeLo not connected, attempting reconnect...")
        service_info = async_last_service_info(self._hass, self._address, connectable=True)
        if service_info is None:
            _LOGGER.warning("LeeLo not visible for reconnect")
            return False
        await self._do_connect(service_info.device)
        return self._device is not None and self._device.is_connected

    async def async_turn_on(self, **kwargs) -> None:
        if not await self._ensure_connected():
            return
        # Sync latest speed and timer from shared state
        saved = self._hass.data.get("membantu_leelo_pending", {}).get(self._address, {})
        if "speed" in saved:
            self._device.set_speed_local(saved["speed"])
        if "timer" in saved:
            self._device.set_timer_local(saved["timer"])
        await self._device.start()
        self._running_override = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        if not await self._ensure_connected():
            return
        await self._device.stop()
        self._running_override = False
        self.async_write_ha_state()
