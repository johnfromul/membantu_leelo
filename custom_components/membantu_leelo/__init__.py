"""Membantu LeeLo BLE integration for Home Assistant."""
from __future__ import annotations
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

DOMAIN = "membantu_leelo"
_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.All(cv.ensure_list, [vol.Schema({
        vol.Required("address"): cv.string,
        vol.Optional("name", default="LeeLo"): cv.string,
    })])
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data[DOMAIN] = config.get(DOMAIN, [])
    await discovery.async_load_platform(hass, "switch", DOMAIN, {}, config)
    await discovery.async_load_platform(hass, "select", DOMAIN, {}, config)
    await discovery.async_load_platform(hass, "number", DOMAIN, {}, config)
    await discovery.async_load_platform(hass, "sensor", DOMAIN, {}, config)
    return True
