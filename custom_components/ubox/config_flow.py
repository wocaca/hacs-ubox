"""UBox config flow: first screen is cloud account login only.

Cameras attach later per device: Configure -> device list -> tap a device.
Proxy/relay-only entries created by older versions keep working.
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .cloud_api import UboxApi
from .const import (
    CONF_ACCOUNT, CONF_DEVICE, CONF_DEVICES, CONF_HOST, CONF_HTTP_PASS, CONF_HTTP_USER,
    CONF_LIVE, CONF_PASSWORD,
    CONF_PORT, CONF_REGION, CONF_RELAY, CONF_RELAY_PASSWORD, CONF_RELAY_STREAM,
    CONF_RELAY_UID, CONF_RELAY_USERNAME, CONF_SCAN, CONF_STREAM, CONF_UID,
    CONF_USERNAME, DEFAULT_PORT,
    DEFAULT_REGION, DEFAULT_RELAY, DEFAULT_SCAN, DEFAULT_STREAM,
    DEFAULT_USERNAME, DOMAIN, MODE_CLOUD, MODE_PROXY, MODE_RELAY, REGIONS,
)


class UboxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None) -> FlowResult:
        # 添加时只登录云账号并拉设备列表。
        errors: dict = {}
        if user_input is not None:
            account = (user_input.get(CONF_ACCOUNT) or "").strip()
            password = user_input.get(CONF_PASSWORD) or ""
            region = user_input.get(CONF_REGION, DEFAULT_REGION)
            if not account or not password:
                errors["base"] = "missing_account"
            else:
                try:
                    from homeassistant.helpers.aiohttp_client import async_get_clientsession

                    api = UboxApi(async_get_clientsession(self.hass), account, password, region)
                    ok, real_region = await api.login()
                    if not ok:
                        errors["base"] = "cannot_connect"
                    else:
                        await self.async_set_unique_id(f"{DOMAIN}:{account}:{real_region}")
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"UBox {account} ({real_region})",
                            data={CONF_ACCOUNT: account, CONF_PASSWORD: password,
                                  CONF_REGION: real_region, "entry_kind": MODE_CLOUD},
                        )
                except Exception:  # noqa: BLE001 - login network errors are user-facing
                    errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ACCOUNT): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_REGION, default=DEFAULT_REGION): vol.In(list(REGIONS)),
            }),
            errors=errors,
        )

    # ---- legacy steps (kept so old URLs abort cleanly; no longer reachable) ----
    async def async_step_proxy(self, user_input=None) -> FlowResult:
        return self.async_abort(reason="use_cloud_first")

    async def async_step_relay(self, user_input=None) -> FlowResult:
        return self.async_abort(reason="use_cloud_first")

    async def async_step_cloud(self, user_input=None) -> FlowResult:
        return await self.async_step_user(user_input)

    @staticmethod
    def async_get_options_flow(entry):
        return UboxOptionsFlow(entry)


class UboxOptionsFlow(config_entries.OptionsFlow):
    """配置 = 设备列表，点进一台配它的实时/中继。Add-on 主机自动取 HASS 本机。"""

    def __init__(self, entry) -> None:
        self._entry = entry
        self._device_uid: str = ""
        self._http_user: str = ""
        self._http_pass: str = ""

    def _devices(self) -> list:
        try:
            store = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
            coord = store.get("coordinator")
            return ((coord.data or {}).get("devices", []) or []) if coord else []
        except Exception:  # noqa: BLE001 - coordinator missing means manual fill
            return []

    def _find(self, uid: str) -> dict:
        for d in self._devices():
            if d.get("uid") == uid:
                return d
        return {}

    def _saved(self) -> dict:
        merged = {**self._entry.data, **self._entry.options}
        return merged.get(CONF_DEVICES, {}) or {}

    async def async_step_init(self, user_input=None) -> FlowResult:
        merged = {**self._entry.data, **self._entry.options}
        if self._entry.data.get("entry_kind", MODE_CLOUD) != MODE_CLOUD:
            # 旧独立 proxy 条目：只需要补 Add-on 鉴权
            if user_input is not None:
                opts = dict(self._entry.options)
                opts[CONF_HTTP_USER] = (user_input.get(CONF_HTTP_USER) or "").strip()
                opts[CONF_HTTP_PASS] = user_input.get(CONF_HTTP_PASS) or ""
                return self.async_create_entry(title="", data=opts)
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({
                    vol.Optional(CONF_HTTP_USER, default=merged.get(CONF_HTTP_USER, "")): str,
                    vol.Optional(CONF_HTTP_PASS, default=merged.get(CONF_HTTP_PASS, "")): str,
                }),
            )
        devs = {d.get("uid", ""): f"{d.get('name') or d.get('uid', '')}"
                for d in self._devices() if d.get("uid")}
        if not devs:
            return self.async_abort(reason="no_devices")
        if user_input is not None:
            self._device_uid = user_input.get(CONF_DEVICE) or next(iter(devs))
            self._http_user = (user_input.get(CONF_HTTP_USER) or "").strip()
            self._http_pass = user_input.get(CONF_HTTP_PASS) or ""
            if self._device_uid:
                return await self.async_step_device()
        if len(devs) == 1 and user_input is None:
            self._device_uid = next(iter(devs))
            self._http_user = merged.get(CONF_HTTP_USER, "")
            self._http_pass = merged.get(CONF_HTTP_PASS, "")
            return await self.async_step_device()
        saved_uids = set(self._saved())
        default = next((u for u in devs if u in saved_uids), next(iter(devs)))
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE, default=default): vol.In(devs),
                vol.Optional(CONF_HTTP_USER, default=merged.get(CONF_HTTP_USER, "")): str,
                vol.Optional(CONF_HTTP_PASS, default=merged.get(CONF_HTTP_PASS, "")): str,
            }),
        )

    async def async_step_device(self, user_input=None) -> FlowResult:
        merged = {**self._entry.data, **self._entry.options}
        dev = self._find(self._device_uid)
        if not dev:
            return self.async_abort(reason="no_devices")
        uid = dev.get("uid", "")
        cfg = (merged.get(CONF_DEVICES, {}) or {}).get(uid, {})
        if user_input is not None:
            all_cfg = dict((merged.get(CONF_DEVICES, {}) or {}))
            all_cfg[uid] = {
                CONF_LIVE: bool(user_input.get(CONF_LIVE, True)),
                CONF_PORT: int(user_input.get(CONF_PORT, DEFAULT_PORT) or DEFAULT_PORT),
                CONF_RELAY_USERNAME: user_input.get(CONF_RELAY_USERNAME, DEFAULT_USERNAME),
                CONF_RELAY_PASSWORD: user_input.get(CONF_RELAY_PASSWORD) or "",
                CONF_RELAY: (user_input.get(CONF_RELAY) or "").strip(),
                CONF_RELAY_STREAM: int(user_input.get(CONF_RELAY_STREAM, DEFAULT_STREAM)),
                CONF_SCAN: int(user_input.get(CONF_SCAN, DEFAULT_SCAN)),
            }
            opts = dict(self._entry.options)
            opts[CONF_DEVICES] = all_cfg
            opts[CONF_HTTP_USER] = self._http_user
            opts[CONF_HTTP_PASS] = self._http_pass
            return self.async_create_entry(title="", data=opts)
        auto_user = dev.get("device_user") or DEFAULT_USERNAME
        auto_pwd = dev.get("device_pwd") or ""
        online = "在线" if dev.get("online") else "离线"
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({
                vol.Optional(CONF_LIVE, default=cfg.get(CONF_LIVE, True)): bool,
                vol.Optional(CONF_PORT, default=cfg.get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Optional(CONF_RELAY_USERNAME, default=cfg.get(CONF_RELAY_USERNAME, auto_user)): str,
                vol.Optional(CONF_RELAY_PASSWORD, default=cfg.get(CONF_RELAY_PASSWORD, auto_pwd)): str,
                vol.Optional(CONF_RELAY, default=cfg.get(CONF_RELAY, DEFAULT_RELAY)): str,
                vol.Optional(CONF_RELAY_STREAM, default=cfg.get(CONF_RELAY_STREAM, DEFAULT_STREAM)): int,
                vol.Optional(CONF_SCAN, default=cfg.get(CONF_SCAN, DEFAULT_SCAN)): int,
            }),
            description_placeholders={
                "name": dev.get("name") or uid,
                "uid": uid,
                "status": f"{online} / 电量{dev.get('battery', '?')}%",
            },
        )
