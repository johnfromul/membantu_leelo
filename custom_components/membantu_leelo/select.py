"""Membantu LeeLo – Select entity (timer)."""
from __future__ import annotations
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)
DOMAIN = "membantu_leelo"
STORAGE_KEY = "membantu_leelo_state"
STORAGE_VERSION = 1

TIMER_OPTIONS = ["15 min", "30 min", "45 min", "60 min", "Unlimited"]


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    saved = await store.async_load() or {}

    entities = []
    for d in hass.data.get(DOMAIN, []):
        address = d["address"]
        name = d.get("name", "LeeLo")
        last_timer = saved.get(address, {}).get("timer", "Off")
        entities.append(LeeLoTimer(hass, address, name, store, last_timer))
    async_add_entities(entities)


class LeeLoTimer(SelectEntity):
    _attr_icon = "mdi:timer"
    _attr_options = TIMER_OPTIONS

    def __init__(self, hass, address, name, store, initial_timer):
        self._hass = hass
        self._address = address
        self._store = store
        self._attr_name = f"{name} Timer"
        self._attr_unique_id = f"leelo_timer_{address.replace(':', '')}"
        self._attr_current_option = initial_timer if initial_timer in TIMER_OPTIONS else "Unlimited"

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option

        # Save to persistent storage
        saved = await self._store.async_load() or {}
        saved.setdefault(self._address, {})["timer"] = option
        await self._store.async_save(saved)

        # Update pending state for switch entity
        self._hass.data.setdefault("membantu_leelo_pending", {}).setdefault(self._address, {})["timer"] = option

        # Apply interval to device (works both running and idle)
        device = self._hass.data.get("membantu_leelo_devices", {}).get(self._address)
        if device:
            device.set_timer_local(option)
            if device.is_connected:
                await device.apply_timer(option)

        self.async_write_ha_state()
