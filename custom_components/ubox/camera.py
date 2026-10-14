"""UBox camera platform.

- proxy mode (default): thin wrapper over the hass-ubox Add-on MJPEG
  (http://<host>:<port>/video.mjpg + /snap.jpg). 1080p live today.
- relay mode (experimental): pure-Python port of 脚本/实时视频/拉流_中继.py.
  Yields at best the 360p SUB IDR first fragment; surfaced as a polling
  snapshot camera. No extra pip deps, stdlib + optional ffmpeg binary.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time

import aiohttp
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_HOST, CONF_MODE, CONF_PASSWORD, CONF_PORT, CONF_RELAY, CONF_SCAN,
    CONF_STREAM, CONF_UID, CONF_USERNAME, DEFAULT_SCAN, DOMAIN, MODE_CLOUD,
    MODE_PROXY,
)

_LOGGER = logging.getLogger(__name__)


def _dev_info(dev: dict) -> DeviceInfo:
    """与 sensor/image 同一 device：identifiers (ubox, uid)，三者挂同一设备页。"""
    return DeviceInfo(
        identifiers={(DOMAIN, dev["uid"])},
        name=f"UBox {dev.get('name') or dev['uid']}",
        manufacturer="Ubia",
        model=f"{dev.get('model', '')} / {dev.get('firmware', '')}".strip(" /"),
        serial_number=dev["uid"],
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    if isinstance(data, dict) and data.get("entry_kind") == MODE_CLOUD:
        # cloud entry: per-device cameras from Configure (device list)
        store = data
        host = store.get("addon_host", "")
        devs = {d.get("uid"): d for d in
                ((store.get("coordinator").data or {}).get("devices", []) or []) if d.get("uid")}
        names = {u: (d.get("name") or u) for u, d in devs.items()}
        ents = []
        for uid, port in (store.get("live", {}) or {}).items():
            ents.append(UboxProxyCamera(
                hass, entry, {CONF_HOST: host, CONF_PORT: port},
                name=f"UBox {names.get(uid, uid)} 实时",
                unique_id=f"ubox-{uid}-live",
                device=devs.get(uid)))
        for uid, rcfg in (store.get("relay_cfgs", {}) or {}).items():
            ents.append(UboxRelayCamera(
                hass, entry, dict(rcfg),
                name=f"UBox {names.get(uid, uid)} 中继",
                device=devs.get(uid)))
        if ents:
            async_add_entities(ents)
        return
    if data.get(CONF_MODE, MODE_PROXY) == MODE_PROXY:
        async_add_entities([UboxProxyCamera(hass, entry, data)])
    else:
        async_add_entities([UboxRelayCamera(hass, entry, data)])


class UboxProxyCamera(Camera):
    """Proxy the Add-on MJPEG server as a proper HA camera."""

    def __init__(self, hass, entry, data, name=None, unique_id=None, device=None):
        super().__init__()
        self.hass = hass
        self._entry = entry
        host = data[CONF_HOST]
        port = int(data.get(CONF_PORT, 8089))
        self._mjpeg = f"http://{host}:{port}/video.mjpg"
        self._snap = f"http://{host}:{port}/snap.jpg"
        self._attr_name = name or f"UBox {host}"
        self._attr_unique_id = unique_id or f"ubox-proxy-{host}-{port}"
        if device:
            self._attr_device_info = _dev_info(device)
        # 必须是 Flag 类型：新 HA 在 added_to_hass 里做 `STREAM not in supported_features`，
        # 纯 int 0 会 TypeError 导致实体加不进来（中继实体没设此项所以一直正常）。
        self._attr_supported_features = CameraEntityFeature(0)

    @property
    def frame_interval(self) -> float:
        return 0.5

    async def stream_source(self) -> str | None:
        return self._mjpeg

    async def async_camera_image(self, width=None, height=None) -> bytes | None:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(self._snap, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return None
                return await r.read()
        except Exception as err:  # noqa: BLE001 - network flakiness is normal
            _LOGGER.debug("ubox proxy snap failed: %s", err)
            return None

    @property
    def extra_state_attributes(self):
        return {"mjpeg_url": self._mjpeg, "still_image_url": self._snap,
                "mode": "proxy", "integration": "hacs-ubox"}


def _decode_h265_to_jpeg(h265: bytes, timeout=20) -> bytes | None:
    ff = shutil.which("ffmpeg")
    if not ff or not h265:
        return None
    try:
        p = subprocess.run(
            [ff, "-hide_banner", "-loglevel", "error",
             "-f", "hevc", "-i", "pipe:0",
             "-frames:v", "1", "-f", "mjpeg", "pipe:1"],
            input=h265, capture_output=True, timeout=timeout)
    except Exception:
        return None
    if p.returncode != 0 or len(p.stdout) < 1000:
        return None
    return p.stdout


class UboxRelayCamera(Camera):
    """Experimental pure-Python relay snapshot camera (360p IDR fragment)."""

    def __init__(self, hass, entry, data, name=None, device=None):
        super().__init__()
        self.hass = hass
        self._data = dict(data)
        self._attr_name = name or f"UBox relay {data.get(CONF_UID, '')[:6]}.."
        if device:
            self._attr_device_info = _dev_info(device)
        self._attr_unique_id = f"ubox-relay-{data.get(CONF_UID)}-{data.get(CONF_RELAY)}"
        self._jpeg: bytes | None = None
        self._last_ok: float | None = None
        self._last_try: float | None = None
        self._info: dict = {}
        self._lock = asyncio.Lock()

    @property
    def frame_interval(self) -> float:
        return 1.0

    async def stream_source(self) -> str | None:
        # No live stream in relay mode until video ACK is implemented.
        return None

    async def async_update(self) -> None:
        scan = int(self._data.get(CONF_SCAN, DEFAULT_SCAN))
        now = time.time()
        if self._last_try and now - self._last_try < max(scan, 10):
            return
        async with self._lock:
            if self._last_try and time.time() - self._last_try < max(scan, 10):
                return
            self._last_try = time.time()
            jpeg, info = await self.hass.async_add_executor_job(self._blocking_poll)
            if jpeg:
                self._jpeg = jpeg
                self._last_ok = time.time()
            self._info = info

    def _blocking_poll(self):
        from .p2p.client import fetch_snapshot

        d = self._data
        relay_s = str(d.get(CONF_RELAY, ""))
        host, _, port_s = relay_s.rpartition(":")
        try:
            relay = (host.strip(), int(port_s))
        except ValueError:
            return None, {"ok": False, "note": f"bad relay '{relay_s}'"}
        res = fetch_snapshot(
            uid=d.get(CONF_UID, "").encode(),
            pwd=d.get(CONF_PASSWORD, "").encode(),
            relay=relay,
            stream=int(d.get(CONF_STREAM, 0)),
            timeout=18.0,
        )
        if not res.get("ok"):
            return None, res
        jpeg = _decode_h265_to_jpeg(res["h265"])
        info = {k: v for k, v in res.items() if k != "h265"}
        info["jpeg"] = bool(jpeg)
        # username kept out of state on purpose (no secret leak)
        info.pop("password", None)
        return jpeg, info

    async def async_camera_image(self, width=None, height=None) -> bytes | None:
        await self.async_update()
        return self._jpeg

    @property
    def extra_state_attributes(self):
        out = {"mode": "relay-experimental", "integration": "hacs-ubox",
               "ceiling": "360p IDR snapshot; 1080p needs proxy mode",
               "last_ok": self._last_ok, "last_try": self._last_try}
        out.update(self._info or {})
        out.pop("h265", None)
        return out
