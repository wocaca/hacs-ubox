# UBox HACS Integration

HACS → 自定义仓库（Integration）→ **UBox** → 下载 → 重启 → 添加集成。

- **代理模式（推荐，1080p）：** 填 Add-on 主机+端口，实体即出实时流（`video.mjpg`）与快照（`snap.jpg`）。
- **中继模式（实验，360p 快照）：** 填 UID/admin/密码/中继，轮询取 IDR 首片（无连续视频，未实现 0x1403 ACK）。
