"""UBox cloud snapshot image: one image entity per device, latest cloud event.

Each list/v2 item carries img_url (signed thumbnail URL). State attributes keep
the guid/type/time plus the get_video_url params so a future service can resolve
playback without re-querying.
"""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


def _dev_info(dev: dict) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, dev["uid"])},
        name=f"UBox {dev.get('name') or dev['uid']}",
        manufacturer="Ubia",
        model=f"{dev.get('model', '')} / {dev.get('firmware', '')}".strip(" /"),
        serial_number=dev["uid"],
    )


def _event_time(item: dict) -> datetime | None:
    for key in ("begin", "et_utc", "bt_utc", "start"):
        ts = item.get(key)
        if isinstance(ts, (int, float)) and ts > 0:
            if ts > 1e12:  # ms epoch
                ts = ts / 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    return None


class UboxCloudImage(CoordinatorEntity, ImageEntity):
    """Latest cloud event of one device as a viewable image."""

    _attr_has_entity_name = True
    _attr_content_type = "image/jpeg"

    def __init__(self, coordinator, dev: dict) -> None:
        super().__init__(coordinator)
        self._uid = dev["uid"]
        self._attr_unique_id = f"{DOMAIN}_{dev['uid']}_cloudimg"
        self._attr_name = "云录像快照"
        self._attr_device_info = _dev_info(dev)
        self._bytes: bytes | None = None
        self._guid: str | None = None

    def _item(self) -> dict:
        items = ((self.coordinator.data.get("cloud", {}) or {}).get(self._uid, {}) or {}).get("items", []) or []
        if items and isinstance(items[0], dict):
            return items[0]
        return {}

    @property
    def extra_state_attributes(self):
        it = self._item()
        if not it:
            return {"event": None}
        keep = {k: it.get(k) for k in (
            "guid", "itemid", "type", "event_type", "begin", "end",
            "et_utc", "bt_utc", "bucket_name", "cloud_provider",
            "cloud_provider_int", "endpoint", "image", "uid",
        ) if it.get(k) is not None}
        t = _event_time(it)
        if t is not None:
            keep["event_time"] = t.isoformat()
        return {"event": keep}

    async def async_image(self) -> bytes | None:
        it = self._item()
        url = it.get("img_url") or it.get("image") or ""
        guid = str(it.get("guid") or it.get("itemid") or url)
        if not url or not isinstance(url, str):
            return None
        if self._bytes is not None and guid == self._guid:
            return self._bytes
        session = getattr(self.coordinator, "_ubox_session", None)
        if session is None:
            return self._bytes
        try:
            async with session.get(url, timeout=20) as r:
                if r.status != 200:
                    return self._bytes
                body = await r.read()
        except Exception:  # noqa: BLE001 - flaky signed URLs stay on last frame
            return self._bytes
        if len(body) < 500:
            return self._bytes
        self._bytes = body
        self._guid = guid
        return body


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add: AddEntitiesCallback) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator = store["coordinator"]
    # shared aiohttp session (owned by HA) for thumbnail fetches; kept on the
    # coordinator object so data refreshes (which replace .data) don't drop it
    coordinator._ubox_session = store["api"]._s
    devices = (coordinator.data or {}).get("devices", []) or []
    async_add([UboxCloudImage(coordinator, dev) for dev in devices])
