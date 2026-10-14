"""UBox 云端 API（aiohttp 异步版，逻辑对齐脚本/云端/服务器.py）."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

import aiohttp

from .const import CLOUD_LIST_DAYS, REGIONS


def app_password(pwd: str) -> str:
    """与服务器.py app_password 同算法：空 key HMAC-SHA1 + 变体 base64."""
    mac = hmac.new(b"", pwd.encode("utf-8"), hashlib.sha1).digest()
    return (
        base64.b64encode(mac)
        .decode("ascii")
        .replace("+", "-")
        .replace("/", "_")
        .replace("=", ",")
    )


class UboxApi:
    """持有 account/region/token，会话失效时自动重登一次。"""

    def __init__(self, session: aiohttp.ClientSession, account: str, password: str, region: str) -> None:
        self._s = session
        self.account = account
        self._pwd = password
        self.region = region if region in REGIONS else "us"
        self.token: str = ""

    def _base(self, region: str | None = None) -> str:
        return REGIONS.get(region or self.region, REGIONS["cn"])

    async def _post(self, path: str, body: dict, token: str = "", base: str | None = None, retry: bool = True):
        url = (base or self._base()) + path
        headers = {"Content-Type": "application/json", "X-Ubia-Auth-UserToken": token}
        async with self._s.post(url, json=body, headers=headers, timeout=30) as r:
            txt = await r.text()
            if r.status in (401, 403) and retry and self.account and self._pwd:
                ok, _ = await self.login()
                if ok:
                    return await self._post(path, body, self.token, base, retry=False)
                raise RuntimeError(f"HTTP {r.status}: {txt[:300]}")
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}: {txt[:300]}")
            import json as _j

            return _j.loads(txt or "{}")

    async def _login_region(self, region: str):
        body = {
            "account": self.account,
            "password": app_password(self._pwd),
            "app": "ubox",
            "app_version": "1.1.370",
            "brand": "android",
            "lang": "zh_CN",
            "device_type": 1,
        }
        data = await self._post("/api/pub/account/login/v3", body, "", REGIONS[region], retry=False)
        token = (data.get("data") or {}).get("Token", "")
        if not token:
            raise RuntimeError(f"login empty token region={region}")
        return token

    async def login(self):
        """逐 region 登录，设备列表非空优先（对齐 auto_login_regions）。"""
        order = [self.region] + [r for r in REGIONS if r != self.region]
        fallback = None
        last_err: Exception | None = None
        for rg in order:
            try:
                token = await self._login_region(rg)
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
            try:
                items = await self._device_items(token, REGIONS[rg])
            except Exception as e:  # noqa: BLE001
                last_err = e
                if fallback is None:
                    fallback = (token, rg)
                continue
            if items:
                self.token, self.region = token, rg
                return True, rg
            if fallback is None:
                fallback = (token, rg)
        if fallback:
            self.token, self.region = fallback
            return True, fallback[1]
        return False, str(last_err or "all regions failed")

    async def _device_items(self, token: str, base: str):
        data = await self._post("/api/v2/user/device_list", {}, token, base, retry=False)
        return (data.get("data", {}) or {}).get("items", []) or []

    @staticmethod
    def merge_devices(raw: dict) -> list[dict]:
        """合并 items + infos + firmware_ver（对齐服务器.py /api/devices，取传感器子集+全量 attributes）。"""
        d = raw.get("data", {}) or {}
        items = d.get("items", []) or []
        infos = d.get("infos", []) or []
        fw = d.get("firmware_ver", []) or []
        fw_map = {str(f.get("model_num")): f.get("version") for f in fw if isinstance(f, dict)}
        info_map = {i["device_uid"]: i for i in infos if isinstance(i, dict) and i.get("device_uid")}
        out: list[dict] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            uid = it.get("device_uid") or it.get("uid", "")
            inf = info_map.get(uid, {}) or {}
            dyn = inf.get("dynamic_info", {}) or {}
            model = inf.get("model_num") or it.get("device_model") or it.get("model", "")
            st = dyn.get("online_state", "")
            out.append(
                {
                    "uid": uid,
                    "name": it.get("device_name") or inf.get("device_name") or it.get("name", uid),
                    "model": str(model),
                    "firmware": fw_map.get(str(model), ""),
                    "online": str(st) in ("1", "2"),
                    "online_state": st,
                    "battery": dyn.get("battery"),
                    "charging": bool(dyn.get("is_battery_charging", False)),
                    "signal": dyn.get("signal"),
                    "low_power": bool(dyn.get("is_low_power", False)),
                    "last_active_utc": dyn.get("latest_active_utc"),
                    "has_cloud_storage": bool(inf.get("has_cloud_storage", False)),
                    "cloud_opened": bool(inf.get("is_cloud_storage_opened", False)),
                    "is_owner": it.get("is_owner", inf.get("is_owner", False)),
                    "device_user": inf.get("device_user", ""),
                    "has_pwd": bool(inf.get("device_pwd")),
                    # device_pwd 明文绝不进 attributes（对齐服务器.py 掩码策略）
                    "raw_item": it,
                    "raw_info": {k: v for k, v in inf.items() if k != "device_pwd"},
                }
            )
        return out

    async def fetch_all(self) -> dict:
        """一次轮询全部：设备列表 + 用户资料 + 各设备近7天云录像计数/最新一条。"""
        if not self.token:
            ok, _ = await self.login()
            if not ok:
                raise RuntimeError("login failed")
        raw = await self._post("/api/v2/user/device_list", {}, self.token)
        devices = self.merge_devices(raw)
        try:
            myinfo = await self._post(
                "/api/user/qry/account/myinfo", {"store_country_region_code": ""}, self.token
            )
        except Exception:  # noqa: BLE001
            myinfo = {}
        cloud: dict = {}
        now = int(time.time())
        for dev in devices:
            uid = dev["uid"]
            try:
                lst = await self._post(
                    "/api/user/qry/cloudvideo/list/v2",
                    {"begin": now - CLOUD_LIST_DAYS * 86400, "end": now, "device_uids": [uid]},
                    self.token,
                )
                items = ((lst.get("data") or {}).get("items", []) or [])
                latest = items[0] if items else {}
                cloud[uid] = {"count": len(items), "latest": latest}
            except Exception:  # noqa: BLE001
                cloud[uid] = {"count": None, "latest": {}}
        total = len(devices)
        online = sum(1 for x in devices if x["online"])
        return {
            "devices": devices,
            "myinfo": (myinfo.get("data") or myinfo) if isinstance(myinfo, dict) else {},
            "cloud": cloud,
            "stats": {
                "total": total,
                "online": online,
                "offline": total - online,
                "mine": sum(1 for x in devices if x.get("is_owner")),
                "shared": sum(1 for x in devices if not x.get("is_owner")),
            },
        }
