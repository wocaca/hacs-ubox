"""UBox config flow: first screen is cloud account login only.

Everything else (live video via Add-on, relay P2P camera) is attached later
from the entry's Configure button (options flow). Proxy/relay-only entries
created by older versions keep working; new adds all start from cloud.
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .cloud_api import UboxApi
from .const import (
    CONF_ACCOUNT, CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_REGION, CONF_RELAY,
    CONF_RELAY_PASSWORD, CONF_RELAY_STREAM, CONF_RELAY_UID, CONF_RELAY_USERNAME,
    CONF_SCAN, CONF_STREAM, CONF_UID, CONF_USERNAME, DEFAULT_PORT,
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
    """事后配置：实时视频（Add-on 地址）+ 中继摄像头（UID/密码/中继），留空即不要。"""

    def __init__(self, entry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        if self._entry.data.get("entry_kind", MODE_CLOUD) != MODE_CLOUD:
            return self.async_abort(reason="camera_no_options")
        merged = {**self._entry.data, **self._entry.options}
        if user_input is not None:
            host = (user_input.get(CONF_HOST) or "").strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT) or DEFAULT_PORT)
            r_uid = (user_input.get(CONF_RELAY_UID) or "").strip()
            r_pwd = user_input.get(CONF_RELAY_PASSWORD) or ""
            r_relay = (user_input.get(CONF_RELAY) or "").strip()
            data: dict = {}
            if host:
                data[CONF_HOST] = host
                data[CONF_PORT] = port
            if r_uid and r_pwd and ":" in r_relay:
                data[CONF_RELAY_UID] = r_uid
                data[CONF_RELAY_USERNAME] = user_input.get(CONF_RELAY_USERNAME, DEFAULT_USERNAME)
                data[CONF_RELAY_PASSWORD] = r_pwd
                data[CONF_RELAY] = r_relay
                data[CONF_RELAY_STREAM] = int(user_input.get(CONF_RELAY_STREAM, DEFAULT_STREAM))
                data[CONF_SCAN] = int(user_input.get(CONF_SCAN, DEFAULT_SCAN))
            return self.async_create_entry(title="", data=data)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_HOST, default=merged.get(CONF_HOST, "")): str,
                vol.Optional(CONF_PORT, default=merged.get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Optional(CONF_RELAY_UID, default=merged.get(CONF_RELAY_UID, "")): str,
                vol.Optional(CONF_RELAY_USERNAME, default=merged.get(CONF_RELAY_USERNAME, DEFAULT_USERNAME)): str,
                vol.Optional(CONF_RELAY_PASSWORD, default=merged.get(CONF_RELAY_PASSWORD, "")): str,
                vol.Optional(CONF_RELAY, default=merged.get(CONF_RELAY, DEFAULT_RELAY)): str,
                vol.Optional(CONF_RELAY_STREAM, default=merged.get(CONF_RELAY_STREAM, DEFAULT_STREAM)): int,
                vol.Optional(CONF_SCAN, default=merged.get(CONF_SCAN, DEFAULT_SCAN)): int,
            }),
        )
