"""Membantu LeeLo – Number entity (speed 1-10)."""
from __future__ import annotations
import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

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
        entities.append(LeeLoSpeed(hass, address, name, store, last_speed))
    async_add_entities(entities)


class LeeLoSpeed(NumberEntity):
    _attr_icon = "mdi:speedometer"
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, hass, address, name, store, initial_speed):
        self._hass = hass
        self._address = address
        self._store = store
        self._attr_name = f"{name} Speed"
        self._attr_unique_id = f"leelo_speed_{address.replace(':', '')}"
        self._attr_native_value = float(initial_speed)

    async def async_set_native_value(self, value: float) -> None:
        speed = int(value)
        self._attr_native_value = float(speed)

        # Save to persistent storage
        saved = await self._store.async_load() or {}
        saved.setdefault(self._address, {})["speed"] = speed
        await self._store.async_save(saved)

        # Update pending state for switch entity
        self._hass.data.setdefault("membantu_leelo_pending", {}).setdefault(self._address, {})["speed"] = speed

        # Apply speed to device immediately if connected
        device = self._hass.data.get("membantu_leelo_devices", {}).get(self._address)
        if device and device.is_connected:
            await device.apply_speed(speed)

        self.async_write_ha_state()
