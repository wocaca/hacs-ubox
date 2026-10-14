"""UBox sensors only：每设备 在线/电量/信号/最后活跃/近7天云录像数 + 单个用户传感器.

对齐 8080 设备页（含云录像计数）+ 用户页（资料+设备统计）。
device_pwd 明文、avatar 签名 URL、Token 一律不进 attributes。
"""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
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


class _Base(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, dev: dict, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._uid = dev["uid"]
        self._key = key
        self._attr_unique_id = f"{DOMAIN}_{dev['uid']}_{key}"
        self._attr_name = name
        self._attr_device_info = _dev_info(dev)

    def _dev(self) -> dict:
        for d in self.coordinator.data.get("devices", []):
            if d.get("uid") == self._uid:
                return d
        return {}


class UboxOnlineSensor(_Base):
    def __init__(self, coordinator, dev: dict) -> None:
        super().__init__(coordinator, dev, "online", "在线状态")
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["online", "offline"]

    @property
    def native_value(self):
        return "online" if self._dev().get("online") else "offline"

    @property
    def extra_state_attributes(self):
        d = self._dev()
        return {"online_state": d.get("online_state"), "uid": self._uid}


class UboxBatterySensor(_Base):
    def __init__(self, coordinator, dev: dict) -> None:
        super().__init__(coordinator, dev, "battery", "电量")
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self):
        return self._dev().get("battery")

    @property
    def extra_state_attributes(self):
        d = self._dev()
        return {"charging": d.get("charging"), "low_power": d.get("low_power")}


class UboxSignalSensor(_Base):
    def __init__(self, coordinator, dev: dict) -> None:
        super().__init__(coordinator, dev, "signal", "信号")
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return self._dev().get("signal")


class UboxLastActiveSensor(_Base):
    def __init__(self, coordinator, dev: dict) -> None:
        super().__init__(coordinator, dev, "last_active", "最后活跃")
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        ts = self._dev().get("last_active_utc")
        if isinstance(ts, int) and ts > 0:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        return None


class UboxCloudSensor(_Base):
    """近7天云录像条数（云录像入口保留的最小形态），最新一条只留 guid/时间。"""

    def __init__(self, coordinator, dev: dict) -> None:
        super().__init__(coordinator, dev, "cloud7d", "近7天云录像")
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        c = (self.coordinator.data.get("cloud", {}) or {}).get(self._uid, {})
        return c.get("count")

    @property
    def extra_state_attributes(self):
        c = (self.coordinator.data.get("cloud", {}) or {}).get(self._uid, {})
        latest = c.get("latest", {}) or {}
        keep = {k: latest.get(k) for k in ("guid", "itemid", "begin", "end", "uid") if latest.get(k) is not None}
        d = self._dev()
        return {
            "has_cloud_storage": d.get("has_cloud_storage"),
            "cloud_opened": d.get("cloud_opened"),
            "latest": keep,
        }


class UboxUserSensor(CoordinatorEntity, SensorEntity):
    """单个用户传感器：值为设备总数，属性带用户资料安全子集 + 设备统计。"""

    _attr_has_entity_name = True

    def __init__(self, coordinator, account: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_user_{account}"
        self._attr_name = "用户信息"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return (self.coordinator.data.get("stats", {}) or {}).get("total")

    @property
    def extra_state_attributes(self):
        myinfo = self.coordinator.data.get("myinfo", {}) or {}
        data = myinfo.get("data", myinfo) if isinstance(myinfo, dict) else {}
        if not isinstance(data, dict):
            data = {}
        safe = {k: data.get(k) for k in ("account", "kuid", "uuid", "email_auth", "lang", "login_node") if k in data}
        safe["wechat_bound"] = bool(data.get("wechat_bind")) if "wechat_bind" in data else None
        extra = ((data.get("extra") or {}) if isinstance(data.get("extra"), dict) else {})
        if extra:
            safe["extra"] = {k: extra.get(k) for k in list(extra)[:8]}
        stats = self.coordinator.data.get("stats", {}) or {}
        return {"user": safe, "stats": stats}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add: AddEntitiesCallback) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator = store["coordinator"]
    devices = (coordinator.data or {}).get("devices", []) or []
    ents: list[SensorEntity] = []
    for dev in devices:
        ents += [
            UboxOnlineSensor(coordinator, dev),
            UboxBatterySensor(coordinator, dev),
            UboxSignalSensor(coordinator, dev),
            UboxLastActiveSensor(coordinator, dev),
            UboxCloudSensor(coordinator, dev),
        ]
    ents.append(UboxUserSensor(coordinator, entry.data.get("account", "")))
    async_add(entities=ents)
