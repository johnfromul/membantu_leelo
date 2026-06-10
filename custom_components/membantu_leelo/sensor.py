"""Membantu LeeLo – Remaining time sensor."""
from __future__ import annotations
import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)
DOMAIN = "membantu_leelo"

INTERVAL_MINUTES = {
    "15 min": 15,
    "30 min": 30,
    "45 min": 45,
    "60 min": 60,
    "Unlimited": None,
}


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    entities = []
    for d in hass.data.get(DOMAIN, []):
        address = d["address"]
        name = d.get("name", "LeeLo")
        entities.append(LeeLoRemaining(hass, address, name))
    async_add_entities(entities)


class LeeLoRemaining(SensorEntity):
    _attr_icon = "mdi:timer-sand"

    def __init__(self, hass: HomeAssistant, address: str, name: str):
        self._hass = hass
        self._address = address
        self._attr_name = f"{name} Remaining"
        self._attr_unique_id = f"leelo_remaining_{address.replace(':', '')}"
        self._attr_native_value = "—"
        self._cancel_timer = None

    async def async_added_to_hass(self) -> None:
        async def _tick(now):
            self._update_value()
            self.async_write_ha_state()
        self._cancel_timer = async_track_time_interval(
            self._hass, _tick, timedelta(seconds=10)
        )
        self._update_value()

    async def async_will_remove_from_hass(self) -> None:
        if self._cancel_timer:
            self._cancel_timer()

    def _update_value(self) -> None:
        device = self._hass.data.get("membantu_leelo_devices", {}).get(self._address)
        if device is None or not device.is_connected or not device.is_running:
            self._attr_native_value = "—"
            return

        timer = device.timer
        if timer == "Unlimited":
            self._attr_native_value = "Unlimited"
            return

        # Compute remaining from start time stored on device
        remaining = device.remaining_seconds()
        if remaining is None or remaining <= 0:
            self._attr_native_value = "—"
            return
        mins = remaining // 60
        secs = remaining % 60
        self._attr_native_value = f"{mins:02d}:{secs:02d}"
