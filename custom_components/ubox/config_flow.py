"""UBox config flow: proxy (Add-on MJPEG, recommended) or relay (pure-Python, experimental)."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_HOST, CONF_MODE, CONF_PASSWORD, CONF_PORT, CONF_RELAY, CONF_SCAN,
    CONF_STREAM, CONF_UID, CONF_USERNAME, DEFAULT_PORT, DEFAULT_RELAY,
    DEFAULT_SCAN, DEFAULT_STREAM, DEFAULT_USERNAME, DOMAIN, MODE_PROXY,
    MODE_RELAY,
)


class UboxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_MODE, default=MODE_PROXY): vol.In({
                        MODE_PROXY: "Proxy (UBox Camera Add-on MJPEG, 1080p)",
                        MODE_RELAY: "Relay direct (pure Python, 360p snapshot, experimental)",
                    }),
                }),
            )
        self._mode = user_input[CONF_MODE]
        if self._mode == MODE_PROXY:
            return await self.async_step_proxy()
        return await self.async_step_relay()

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
