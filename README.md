# TikPlayer

![TikPlayer UI](images/ui/desktop.png)

[![Docker Pulls](https://img.shields.io/docker/pulls/leduchuong/tikplayer?logo=docker&label=Docker%20Pulls)](https://hub.docker.com/r/leduchuong/tikplayer)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Build: Passing](https://img.shields.io/badge/Build-Passing-brightgreen.svg)](#)
[![Platform: ARM64/AMD64](https://img.shields.io/badge/Platform-ARM64%2FAMD64-blue.svg)](#)

[English](README_en.md)

> Better alternative to web-file-player for E-ink devices.

TikPlayer 是一个面向 NAS/HomeLab 的轻量级视频在线播放与管理服务，重点解决“多终端访问、硬解兼容、部署复杂度高”的问题。

## Why this tool?（为什么要做它）

很多家庭服务器用户只想快速搭一个能跑、好看、可远程访问的视频播放器，但经常被繁琐部署、格式兼容和设备适配问题卡住。TikPlayer 把这些常见问题收敛到一个可复制的 Docker 部署流程里，减少试错成本。

## 项目做什么（功能概览）

- Web UI 播放与基础媒体管理
- 面向 Docker/NAS 的快速部署
- ARM64/AMD64 双架构支持

## UI 界面展示

![Desktop UI](images/ui/desktop.png)
![Mobile UI](images/ui/mobile.png)

## ⚡️ Quick Start (Run in 3 seconds)

```bash
docker run -d \
  --name tikplayer \
  --restart unless-stopped \
  -p 1015:8000 \
  -v ./image:/app/image \
  -v ./data:/app/data \
  docker.io/leduchuong/tikplayer:latest
```

## Docker Compose（Portainer / NAS 可直接粘贴）

```yaml
services:
  tikplayer:
    image: docker.io/leduchuong/tikplayer:latest
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

使用本项目即表示你已阅读并同意 [免责声明](DISCLAIMER.md)。

## 许可证

MIT，详见 [LICENSE](LICENSE)。
