# hacs-ubox — UBox HACS Integration（云账号入口）

添加时只输云账号密码；摄像头事后在条目"配置"里加。

`拉流_中继.py`（本地 P2P）+ 云端设备页（`脚本/云端/服务器.py`），做成 HACS 可安装的 Integration（`custom_components/ubox`）。

## 三种用法（一个云条目，全在"配置"里加）

| 部位 | 数据源 | 实体 | 说明 |
|---|---|---|---|
| 添加时 | UBox 账号（portal.ubianet.com，us/cn/uni 自动选） | sensor + image | 只登录+拉设备列表。每设备 ×4 传感器 + ×1 最新云录像快照图；全局 ×1 用户信息。60s 轮询 |
| 配置→实时视频 | `hass-ubox` Add-on `:8089/video.mjpg` + `/snap.jpg` | camera | 填 Add-on 主机即出 1080p 实时实体 |
| 配置→中继摄像头 | 内嵌 `p2p/`（`拉流_中继.py` 自包含移植） | camera | 填 UID/设备密码/中继即出 360p 快照实体（缺 0x1403 视频 ACK，见 ubox 交接 #106） |

**relay 天花板（实测结论，不是 bug）：** 纯 Python 中继只能拿到 360p SUB 的 IDR 首片（含 VPS/SPS/PPS，
约 1264B），连续 GOP 需要 0x1403 视频 ACK（未实现），1080p MAIN 仍走真 so。要 1080p 请用 proxy 模式。

**cloud 口径：** 对齐 `脚本/云端/服务器.py`（device_list 合并 infos/firmware、dynamic_info 折算在线/电量/信号、cloudvideo 近7天计数）。
`device_pwd` 明文、avatar 签名 URL、Token 永不进 attributes。

## 安装（HACS）

1. HACS → 右上 ⋮ → 自定义仓库 → 加 `https://github.com/wocaca/hacs-ubox`，类型 **Integration** → 添加。
2. 搜 **UBox** → 下载 → 重启 HASS。
3. 设置 → 设备与服务 → 添加集成 → **UBox**：只填 UBox 账号 + 密码 + 区服（默认 us，登录时按设备列表非空自动纠偏），即出传感器/图片。
4. 要摄像头：去该条目点"配置"——实时视频填 Add-on 主机+端口；中继摄像头填 UID/设备密码/中继。留空=不要，可随时改。

## 文件结构

```
custom_components/ubox/
  manifest.json  domain=ubox, local_polling, 0.5.0
  __init__.py    cloud 条目：sensor+image 60s Coordinator，配置里加了地址/中继才转发 camera
  config_flow.py 添加=云登录；配置=实时视频+中继摄像头（旧 proxy/relay 独立条目仍兼容）
  camera.py      UboxProxyCamera + UboxRelayCamera
  sensor.py      每设备4传感器 + 用户传感器（device_pwd 不进属性）
  image.py       每设备最新一条云录像一张图（img_url 直取，属性带回放参数）
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
