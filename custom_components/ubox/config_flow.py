"""UBox config flow: proxy camera / relay camera / cloud sensors."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .cloud_api import UboxApi
from .const import (
    CONF_ACCOUNT, CONF_HOST, CONF_MODE, CONF_PASSWORD, CONF_PORT, CONF_REGION,
    CONF_RELAY, CONF_SCAN, CONF_STREAM, CONF_UID, CONF_USERNAME, DEFAULT_PORT,
    DEFAULT_REGION, DEFAULT_RELAY, DEFAULT_SCAN, DEFAULT_STREAM,
    DEFAULT_USERNAME, DOMAIN, MODE_CLOUD, MODE_PROXY, MODE_RELAY, REGIONS,
)


class UboxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_MODE, default=MODE_PROXY): vol.In({
                        MODE_PROXY: "Proxy camera (Add-on MJPEG, 1080p)",
                        MODE_RELAY: "Relay camera (pure Python, snapshot, experimental)",
                        MODE_CLOUD: "Cloud sensors (account devices + user)",
                    }),
                }),
            )
        mode = user_input[CONF_MODE]
        if mode == MODE_PROXY:
            return await self.async_step_proxy()
        if mode == MODE_RELAY:
            return await self.async_step_relay()
        return await self.async_step_cloud()

    async def async_step_proxy(self, user_input=None) -> FlowResult:
        errors: dict = {}
        if user_input is not None:
            host = (user_input.get(CONF_HOST) or "").strip()
            if not host:
                errors[CONF_HOST] = "required"
            else:
                data = {
                    CONF_MODE: MODE_PROXY,
                    CONF_HOST: host,
                    CONF_PORT: int(user_input.get(CONF_PORT, DEFAULT_PORT)),
                }
                await self.async_set_unique_id(f"proxy-{host}:{data[CONF_PORT]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"UBox {host}", data=data)
        return self.async_show_form(
            step_id="proxy",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default="10.1.1.12"): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            }),
            errors=errors,
        )

    async def async_step_relay(self, user_input=None) -> FlowResult:
        errors: dict = {}
        if user_input is not None:
            uid = (user_input.get(CONF_UID) or "").strip()
            pwd = user_input.get(CONF_PASSWORD) or ""
            relay = (user_input.get(CONF_RELAY) or "").strip()
            if not uid:
                errors[CONF_UID] = "required"
            elif not pwd:
                errors[CONF_PASSWORD] = "required"
            elif ":" not in relay:
                errors[CONF_RELAY] = "invalid"
            else:
                data = {
                    CONF_MODE: MODE_RELAY,
                    CONF_UID: uid,
                    CONF_USERNAME: user_input.get(CONF_USERNAME, DEFAULT_USERNAME),
                    CONF_PASSWORD: pwd,
                    CONF_RELAY: relay,
                    CONF_STREAM: int(user_input.get(CONF_STREAM, DEFAULT_STREAM)),
                    CONF_SCAN: int(user_input.get(CONF_SCAN, DEFAULT_SCAN)),
                }
                await self.async_set_unique_id(f"relay-{uid}-{relay}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"UBox {uid[:6]}..", data=data)
        return self.async_show_form(
            step_id="relay",
            data_schema=vol.Schema({
                vol.Required(CONF_UID): str,
                vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_RELAY, default=DEFAULT_RELAY): str,
                vol.Required(CONF_STREAM, default=DEFAULT_STREAM): int,
                vol.Required(CONF_SCAN, default=DEFAULT_SCAN): int,
            }),
            errors=errors,
            description_placeholders={
                "note": "Experimental: 360p IDR snapshot only. 1080p live needs proxy mode."
            },
        )

    async def async_step_cloud(self, user_input=None) -> FlowResult:
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
            step_id="cloud",
            data_schema=vol.Schema({
                vol.Required(CONF_ACCOUNT): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_REGION, default=DEFAULT_REGION): vol.In(list(REGIONS)),
            }),
            errors=errors,
        )
