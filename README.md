# hacs-ubox — UBox HACS Integration（云账号入口）

添加时只输云账号密码；摄像头事后在条目"配置"里加。

`拉流_中继.py`（本地 P2P）+ 云端设备页（`脚本/云端/服务器.py`），做成 HACS 可安装的 Integration（`custom_components/ubox`）。

## 三种用法（一个云条目，全在"配置"里加）

| 部位 | 数据源 | 实体 | 说明 |
|---|---|---|---|
| 添加时 | UBox 账号（portal.ubianet.com，us/cn/uni 自动选） | sensor + image | 只登录+拉设备列表。每设备 ×4 传感器 + ×1 最新云录像快照图；全局 ×1 用户信息。60s 轮询 |
| 配置→设备列表→点进设备 | 本机 Add-on `:8089`（主机自动取 HASS 本机）+ 内嵌 `p2p/` | camera | 实时开关默认开（1080p）；中继填 UID/设备密码/中继即出 360p 快照实体（UID/密码自动带出）。按设备各自开关 |

**relay 天花板（实测结论，不是 bug）：** 纯 Python 中继只能拿到 360p SUB 的 IDR 首片（含 VPS/SPS/PPS，
约 1264B），连续 GOP 需要 0x1403 视频 ACK（未实现），1080p MAIN 仍走真 so。要 1080p 请用 proxy 模式。

**cloud 口径：** 对齐 `脚本/云端/服务器.py`（device_list 合并 infos/firmware、dynamic_info 折算在线/电量/信号、cloudvideo 近7天计数）。
`device_pwd` 明文、avatar 签名 URL、Token 永不进 attributes。

## 安装（HACS）

1. HACS → 右上 ⋮ → 自定义仓库 → 加 `https://github.com/wocaca/hacs-ubox`，类型 **Integration** → 添加。
2. 搜 **UBox** → 下载 → 重启 HASS。
3. 设置 → 设备与服务 → 添加集成 → **UBox**：只填 UBox 账号 + 密码 + 区服（默认 us，登录时按设备列表非空自动纠偏），即出传感器/图片。
4. 要摄像头：去该条目点"配置"→设备列表→点进一台：实时开关默认开（走本机 Add-on，主机自动探测不用填）；中继的 UID/设备密码自动带出，填中继地址即出快照实体。每台设备各自开关。

## 文件结构

```
custom_components/ubox/
  manifest.json  domain=ubox, local_polling, 0.7.0
  __init__.py    cloud 条目：sensor+image 60s Coordinator；按设备配了实时/中继才转发 camera；Add-on 主机自动取 HASS 内部 URL
  config_flow.py 添加=云登录；配置=设备列表→点进设备（实时开关+中继，UID/密码自动带出）
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

## 发版流程（必做，否则 HACS 无版本可选）

HACS 的版本下拉框和更新提示读的是 **GitHub Release 列表**，不是 commit。每次发版：

1. 改 `custom_components/ubox/manifest.json` 的 `version`（如 `0.6.1`）。
2. commit + push 到 main。
3. 发 Release：tag 名与 version **完全一致**（如 `0.6.0`，不要 `v` 前缀），target 选 main。
   ```powershell
   # 例：发 0.6.1（GH_TOKEN 为有 repo 权限的 PAT，用完即删环境变量）
   $env:GH_TOKEN='***'
   $b=@{tag_name='0.6.1'; target_commitish='main'; name='0.6.1'} | ConvertTo-Json
   Invoke-RestMethod -Method Post `
     -Uri 'https://api.github.com/repos/wocaca/hacs-ubox/releases' `
     -Headers @{Authorization='Bearer '+$env:GH_TOKEN; Accept='application/vnd.github+json'} `
     -Body $b -ContentType 'application/json'
   Remove-Item Env:\GH_TOKEN
   ```
4. HACS 侧"更新自定义仓库"后即出现新版本。

## 许可

MIT（协议逆向部分仅供个人学习/自有设备使用）。
