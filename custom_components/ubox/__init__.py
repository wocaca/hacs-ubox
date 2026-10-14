"""UBox HACS integration entry setup: cloud entry with per-device cameras."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .cloud_api import UboxApi
from .const import (
    CONF_ACCOUNT,
    CONF_DEVICES,
    CONF_HOST,
    CONF_HTTP_PASS,
    CONF_HTTP_USER,
    CONF_LIVE,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_REGION,
    CONF_RELAY,
    CONF_RELAY_PASSWORD,
    CONF_RELAY_STREAM,
    CONF_RELAY_UID,
    CONF_RELAY_USERNAME,
    CONF_SCAN,
    CONF_STREAM,
    CONF_UID,
    CONF_USERNAME,
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


def _addon_host(hass: HomeAssistant) -> str:
    """Add-on 跑在 HASS 本机：取内部 URL 的主机名，用户不用填。"""
    try:
        from homeassistant.helpers.network import get_url
        from urllib.parse import urlparse
        url = get_url(hass, allow_external=False, allow_internal=True)
        return urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001 - detection failure means no live camera
        return ""


def _relay_config_for(uid: str, cfg: dict) -> dict:
    pwd = cfg.get(CONF_RELAY_PASSWORD) or ""
    relay = (cfg.get(CONF_RELAY) or "").strip()
    if pwd and ":" in relay:
        return {
            CONF_UID: uid,
            CONF_USERNAME: cfg.get(CONF_RELAY_USERNAME, DEFAULT_USERNAME),
            CONF_PASSWORD: pwd,
            CONF_RELAY: relay,
            CONF_STREAM: int(cfg.get(CONF_RELAY_STREAM, DEFAULT_STREAM)),
            CONF_SCAN: int(cfg.get(CONF_SCAN, DEFAULT_SCAN)),
        }
    return {}


def _device_cfgs(data: dict, devices: list) -> dict:
    """Merge per-device options with legacy global keys (migrated to first device)."""
    cfgs = dict(data.get(CONF_DEVICES, {}) or {})
    if not cfgs and (data.get(CONF_HOST) or data.get(CONF_RELAY_UID)):
        target = data.get(CONF_RELAY_UID) or (devices[0].get("uid") if devices else "")
        if target:
            cfgs[target] = {
                CONF_LIVE: True,
                CONF_PORT: int(data.get(CONF_PORT, DEFAULT_PORT) or DEFAULT_PORT),
                CONF_RELAY_USERNAME: data.get(CONF_RELAY_USERNAME, DEFAULT_USERNAME),
                CONF_RELAY_PASSWORD: data.get(CONF_RELAY_PASSWORD, ""),
                CONF_RELAY: data.get(CONF_RELAY, ""),
                CONF_RELAY_STREAM: int(data.get(CONF_RELAY_STREAM, DEFAULT_STREAM)),
                CONF_SCAN: int(data.get(CONF_SCAN, DEFAULT_SCAN)),
            }
    return cfgs


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
        devices = (coordinator.data or {}).get("devices", []) or []
        host = _addon_host(hass)
        cfgs = _device_cfgs(data, devices)
        live = {u: int(c.get(CONF_PORT, DEFAULT_PORT) or DEFAULT_PORT)
                for u, c in cfgs.items() if c.get(CONF_LIVE) and host}
        relay_cfgs = {u: _relay_config_for(u, c) for u, c in cfgs.items()}
        relay_cfgs = {u: r for u, r in relay_cfgs.items() if r}
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "api": api,
            "coordinator": coordinator,
            "entry_kind": MODE_CLOUD,
            "addon_host": host,
            "live": live,
            "relay_cfgs": relay_cfgs,
            CONF_HTTP_USER: data.get(CONF_HTTP_USER, "") or "",
            CONF_HTTP_PASS: data.get(CONF_HTTP_PASS, "") or "",
            "platforms": ["sensor", "image"] + (["camera"] if (live or relay_cfgs) else []),
        }
        store = hass.data[DOMAIN][entry.entry_id]
        await hass.config_entries.async_forward_entry_setups(entry, store["platforms"])
    else:
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data
        await hass.config_entries.async_forward_entry_setups(entry, ["camera"])
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    if isinstance(store, dict) and store.get("entry_kind") == MODE_CLOUD:
        platforms = store.get("platforms", ["sensor", "image"])
    elif isinstance(store, dict) and CONF_ACCOUNT in _merged(entry):
        platforms = ["sensor", "image"]
    else:
        platforms = ["camera"]
    ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return ok
