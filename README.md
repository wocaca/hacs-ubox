# hacs-ubox — UBox Camera HACS Integration

`拉流_中继.py` 的功能，做成 HACS 可安装的 Integration（`custom_components/ubox`）。

## 两种模式（为什么有两个）

| 模式 | 数据源 | 画质 | 说明 |
|---|---|---|---|
| **proxy（默认，推荐）** | 已有的 `hass-ubox` Add-on `:8089/video.mjpg` + `/snap.jpg` | 1080p 实时 | Add-on 里是真 so 取流，本集成只做 HA camera 包装 |
| **relay（实验性）** | 本仓 `custom_components/ubox/p2p/`（`拉流_中继.py` 的自包含移植） | 360p 快照 | 纯 Python、无依赖；天花板见下 |

**relay 天花板（实测结论，不是 bug）：** 纯 Python 中继只能拿到 360p SUB 的 IDR 首片（含 VPS/SPS/PPS，
约 1264B），连续 GOP 需要 0x1403 视频 ACK（未实现，见 `D:/code/ubox/文档/实时视频/交接.md` #106），
1080p MAIN 仍走真 so。要 1080p 请用 proxy 模式。

## 安装（HACS）

1. HACS → 右上 ⋮ → 自定义仓库 → 加 `https://github.com/wocaca/hacs-ubox`，类型 **Integration** → 添加。
2. 搜 **UBox** → 下载 → 重启 HASS。
3. 设置 → 设备与服务 → 添加集成 → **UBox**：
   - proxy：填 Add-on 主机（一般就是 HASS 本机 IP）+ 端口（默认 8089）。
   - relay：填摄像头 UID / admin / 密码 / 中继 `162.251.63.134:20001` / stream=0 / 轮询>=10s。

## 文件结构

```
custom_components/ubox/
  manifest.json  domain=ubox, iot_class=local_polling
  __init__.py    entry setup/unload
  config_flow.py proxy / relay 两步表单
  camera.py      UboxProxyCamera + UboxRelayCamera
  const.py
  p2p/           crypto.py + handshake.py + client.py（stdlib only）
  strings.json + translations/en.json + zh-Hans.json
```

## 本地验证

```powershell
python -m py_compile (Get-ChildItem -Recurse custom_components -Filter *.py).FullName
python -c "from custom_components.ubox.p2p.crypto import encrypt_packet,decrypt_packet; ..."
```

## 许可

MIT（协议逆向部分仅供个人学习/自有设备使用）。
