# TikPlayer

![TikPlayer UI](https://raw.githubusercontent.com/leduchuong48-byte/tikplayer/main/images/ui/desktop.png)

[![Docker Pulls](https://img.shields.io/docker/pulls/leduchuong/tikplayer?logo=docker&label=Docker%20Pulls)](https://hub.docker.com/r/leduchuong/tikplayer)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/leduchuong48-byte/tikplayer/blob/main/LICENSE)
[![Build: Passing](https://img.shields.io/badge/Build-Passing-brightgreen.svg)](#)
[![Platform: ARM64/AMD64](https://img.shields.io/badge/Platform-ARM64%2FAMD64-blue.svg)](#)

[English](https://github.com/leduchuong48-byte/tikplayer/blob/main/README_en.md)

> Better alternative to web-file-player for E-ink devices.

TikPlayer 是一个面向 NAS/HomeLab 的轻量级视频在线播放与管理服务，重点解决“多终端访问、硬解兼容、部署复杂度高”的问题。

## 版本更新

- `v2.2`：`reload` 从布尔锁升级为“队列 + 进度百分比 + 阶段状态”，新增队列状态接口，避免“显示成功但实际未完成”。
- `v2.2`：新增账号级 `random_enabled`，支持源“仅浏览不参与随机”；并在后端对随机池按路径去重，减少重叠源重复命中。
- `v2.2`：`move/delete` 后按“同后端 + 路径”主动清理随机池脏条目，降低收纳后仍被随机命中的概率。
- `v2.2`：账号管理改为明确的编辑/删除按钮，删除失败反馈更直接。
- `v2.2`：移动端按 Safari/Chrome 规范重构为单一 sticky 顶栏，适配动态视口与安全区，修复文件页堆叠异常。
- `v2.2`：前端缓存策略修复，`/` 返回 `no-store`，避免浏览器（含无痕）命中旧页面。

## Why this tool?（为什么要做它）

很多家庭服务器用户只想快速搭一个能跑、好看、可远程访问的视频播放器，但经常被繁琐部署、格式兼容和设备适配问题卡住。TikPlayer 把这些常见问题收敛到一个可复制的 Docker 部署流程里，减少试错成本。

## 项目做什么（功能概览）

- Web UI 播放与基础媒体管理
- 面向 Docker/NAS 的快速部署
- ARM64/AMD64 双架构支持
  
✅ Perfect for Raspberry Pi & Oracle Cloud Free Tier (ARM)

## UI 界面展示

![Desktop UI](https://raw.githubusercontent.com/leduchuong48-byte/tikplayer/main/images/ui/desktop.png)
![Mobile UI](https://raw.githubusercontent.com/leduchuong48-byte/tikplayer/main/images/ui/mobile.png)

## ⚡️ Quick Start (Run in 3 seconds)

```bash
docker run -d \
  --name tikplayer \
  --restart unless-stopped \
  -p 1015:8000 \
  -v ./image:/app/image \
  -v ./data:/app/data \
  docker.io/leduchuong/tikplayer:2.2
```

## For Portainer/Synology Users

Copy this into Portainer stacks and hit Deploy. Done.

## Docker Compose

```yaml
services:
  tikplayer:
    image: docker.io/leduchuong/tikplayer:2.2
    container_name: tikplayer
    restart: unless-stopped
    ports:
      - "1015:8000"
    volumes:
      - ./image:/app/image
      - ./data:/app/data
    shm_size: "2gb"
```

## GitHub Topics（建议至少 5 个）

`#nas` `#homelab` `#selfhosted` `#synology` `#unraid` `#eink` `#automation`

## 在哪里获得帮助

- Issues: `https://github.com/leduchuong48-byte/tikplayer/issues`

## 维护者与贡献者

- Maintainer: `@leduchuong48-byte`

## 免责声明

使用本项目即表示你已阅读并同意 [免责声明](https://github.com/leduchuong48-byte/tikplayer/blob/main/DISCLAIMER.md)。

## 许可证

MIT，详见 [LICENSE](https://github.com/leduchuong48-byte/tikplayer/blob/main/LICENSE)。
