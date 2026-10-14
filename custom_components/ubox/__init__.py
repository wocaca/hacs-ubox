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
    CONF_RELAY,
    CONF_RELAY_PASSWORD,
    CONF_RELAY_STREAM,
    CONF_RELAY_UID,
    CONF_RELAY_USERNAME,
    CONF_SCAN,
    DEFAULT_PORT,
    DEFAULT_REGION,
    DEFAULT_SCAN,
    DEFAULT_STREAM,
    DEFAULT_USERNAME,
    DOMAIN,
    MODE_CLOUD,
    UPDATE_INTERVAL_SEC,
)

import logging

_LOGGER = logging.getLogger(__name__)


def _merged(entry: ConfigEntry) -> dict:
    return {**entry.data, **entry.options}


def _relay_config(data: dict) -> dict:
    """Options-attached relay camera config, or {} when not configured."""
    uid = (data.get(CONF_RELAY_UID) or "").strip() if isinstance(data.get(CONF_RELAY_UID), str) else ""
    pwd = data.get(CONF_RELAY_PASSWORD) or ""
    relay = data.get(CONF_RELAY, "") or ""
    if uid and pwd and ":" in str(relay):
        from .const import CONF_STREAM, CONF_UID, CONF_USERNAME
        return {
            CONF_UID: uid,
            CONF_USERNAME: data.get(CONF_RELAY_USERNAME, DEFAULT_USERNAME),
            CONF_PASSWORD: pwd,
            CONF_RELAY: str(relay).strip(),
            CONF_STREAM: int(data.get(CONF_RELAY_STREAM, DEFAULT_STREAM)),
            CONF_SCAN: int(data.get(CONF_SCAN, DEFAULT_SCAN)),
        }
    return {}


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
            "relay": _relay_config(data),
        }
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "image"])
        if data.get(CONF_HOST) or _relay_config(data):
            # optional cameras attached later via Configure
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
        if data.get(CONF_HOST) or _relay_config(data):
            platforms.append("camera")
    else:
        platforms = ["camera"]
    ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return ok
