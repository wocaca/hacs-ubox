"""UBox HACS integration entry setup: camera entries vs cloud-sensor entries."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .cloud_api import UboxApi
from .const import (
    CONF_ACCOUNT,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_REGION,
    DEFAULT_PORT,
    DEFAULT_REGION,
    DOMAIN,
    MODE_CLOUD,
    UPDATE_INTERVAL_SEC,
)

import logging

_LOGGER = logging.getLogger(__name__)


def _merged(entry: ConfigEntry) -> dict:
    return {**entry.data, **entry.options}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = _merged(entry)
    if data.get("entry_kind", "camera") == MODE_CLOUD or CONF_ACCOUNT in data:
        session = async_get_clientsession(hass)
        api = UboxApi(
            session,
            data[CONF_ACCOUNT],
            data[CONF_PASSWORD],
            data.get(CONF_REGION, DEFAULT_REGION),
        )

        async def _update():
            return await api.fetch_all()

        coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN} {data.get(CONF_ACCOUNT, '')}",
            update_method=_update,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SEC),
        )
        await coordinator.async_config_entry_first_refresh()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "api": api,
            "coordinator": coordinator,
            "entry_kind": MODE_CLOUD,
            CONF_HOST: data.get(CONF_HOST, ""),
            CONF_PORT: int(data.get(CONF_PORT, DEFAULT_PORT) or DEFAULT_PORT),
        }
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "image"])
        if data.get(CONF_HOST):
            # optional live video via Add-on MJPEG, configured in options
            await hass.config_entries.async_forward_entry_setups(entry, ["camera"])
    else:
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data
        await hass.config_entries.async_forward_entry_setups(entry, ["camera"])
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = _merged(entry)
    if isinstance(hass.data.get(DOMAIN, {}).get(entry.entry_id), dict) and (
            data.get("entry_kind") == MODE_CLOUD or CONF_ACCOUNT in data):
        platforms = ["sensor", "image"]
        if data.get(CONF_HOST):
            platforms.append("camera")
    else:
        platforms = ["camera"]
    ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return ok
