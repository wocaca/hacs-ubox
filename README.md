# hacs-ubox — UBox Camera + Sensors HACS Integration

`拉流_中继.py`（本地 P2P）+ 云端设备页（`脚本/云端/服务器.py`），做成 HACS 可安装的 Integration（`custom_components/ubox`）。

## 三种条目（一个集成，三种加法）

| 模式 | 数据源 | 实体 | 说明 |
|---|---|---|---|
| **proxy（推荐）** | `hass-ubox` Add-on `:8089/video.mjpg` + `/snap.jpg` | camera | 1080p 实时，今日可用 |
| **relay（实验性）** | 内嵌 `p2p/`（`拉流_中继.py` 自包含移植） | camera | 纯 Python、无依赖；天花板 360p IDR 首片快照（缺 0x1403 视频 ACK，见 ubox 交接 #106） |
| **cloud（新增）** | UBox 账号（portal.ubianet.com，us/cn/uni 自动选） | sensor | 每设备 ×5：在线状态 / 电量% / 信号 / 最后活跃 / 近7天云录像数；全局 ×1：用户信息（值为设备总数）。60s 轮询，登录即验活 |

**relay 天花板（实测结论，不是 bug）：** 纯 Python 中继只能拿到 360p SUB 的 IDR 首片（含 VPS/SPS/PPS，
约 1264B），连续 GOP 需要 0x1403 视频 ACK（未实现），1080p MAIN 仍走真 so。要 1080p 请用 proxy 模式。

**cloud 口径：** 对齐 `脚本/云端/服务器.py`（device_list 合并 infos/firmware、dynamic_info 折算在线/电量/信号、cloudvideo 近7天计数）。
`device_pwd` 明文、avatar 签名 URL、Token 永不进 attributes。

## 安装（HACS）

1. HACS → 右上 ⋮ → 自定义仓库 → 加 `https://github.com/wocaca/hacs-ubox`，类型 **Integration** → 添加。
2. 搜 **UBox** → 下载 → 重启 HASS。
3. 设置 → 设备与服务 → 添加集成 → **UBox**，选一种：
   - proxy：填 Add-on 主机（一般就是 HASS 本机 IP）+ 端口（默认 8089）。
   - relay：填摄像头 UID / admin / 密码 / 中继 `162.251.63.134:20001` / stream=0 / 轮询>=10s。
   - cloud：填 UBox 账号 + 密码 + 区服（默认 us，登录时按设备列表非空自动纠偏）。

## 文件结构

```
custom_components/ubox/
  manifest.json  domain=ubox, local_polling, 0.2.0
  __init__.py    camera 条目 vs cloud 条目分流（sensor 60s Coordinator）
  config_flow.py proxy / relay / cloud 三步表单
  camera.py      UboxProxyCamera + UboxRelayCamera
  sensor.py      每设备5传感器 + 用户传感器（device_pwd 不进属性）
  cloud_api.py   云端 aiohttp 接口（app_password/HMAC-SHA1、逐区服登录、401自动重登）
  const.py
  p2p/           crypto.py + handshake.py + client.py（stdlib only）
  strings.json + translations/en.json + zh-Hans.json
```

## 本地验证

```powershell
python3 -m py_compile (Get-ChildItem -Recurse custom_components -Filter *.py).FullName
```

## 许可

MIT（协议逆向部分仅供个人学习/自有设备使用）。
