<h1 align="center">Tikplayer</h1>

<p align="center">
<a href="https://github.com/leduchuong48-byte/tikplayer/releases"><img alt="Release" src="https://img.shields.io/github/v/release/leduchuong48-byte/tikplayer?display_name=tag"></a>
<a href="https://hub.docker.com/r/leduchuong/tikplayer"><img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/leduchuong/tikplayer?logo=docker"></a>
<a href="https://github.com/leduchuong48-byte/tikplayer/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/leduchuong48-byte/tikplayer"></a>
<a href="https://github.com/leduchuong48-byte/tikplayer/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/leduchuong48-byte/tikplayer"></a>
</p>

<h3 align="center">
  <a href="README_en.md">English</a><span> · </span>
  <a href="https://github.com/leduchuong48-byte/tikplayer/issues">报告问题</a>
  <span> · </span>
  <a href="https://github.com/leduchuong48-byte/tikplayer/discussions">讨论</a>
</h3>

## 概述

Tikplayer 是一个面向 NAS / HomeLab 场景的轻量媒体播放与目录聚合 Web 应用，支持多源目录浏览、播放控制、文件操作和快速收纳。

## 界面

### Web 管理台（2.4）

> 应隐私要求，本版本文档不再展示运行界面截图。
> 如需查看演示界面，请在隔离演示环境中本地预览。

## 支持

| 类别 | 支持 |
|---|---|
| 运行方式 | FastAPI + Web UI |
| 主要场景 | 媒体播放、目录浏览、快速收纳、基础文件操作 |
| 部署 | Docker / Docker Compose / N97 |

## 安装

```bash
git clone https://github.com/leduchuong48-byte/tikplayer.git
cd tikplayer
cp .env.example .env
```

## Docker 容器

```bash
docker pull leduchuong/tikplayer:latest
```

```yaml
services:
  tikplayer:
    image: leduchuong/tikplayer:latest
    container_name: tikplayer
    restart: unless-stopped
    ports:
      - "1015:8000"
    env_file:
      - .env
    volumes:
      - ./image:/app/image
      - ./data:/app/data
      - ./index.html:/app/index.html:ro
```

## 配置

- 核心配置：`sources.json`、`folders.json`
- 运行环境：`.env`
- 建议生产环境启用鉴权并配置白名单。

## 2.4 升级说明（对比 2.3）

- 升级版本标识为 `2.4`，统一 Dockerfile / UI 标识。
- Web UI 交互增强：底部导航流程更清晰，目录返回按钮更易用。
- 文件夹配置模型增强：新增唯一 ID、启用状态、排序、备注、使用时间等字段，管理更稳定。
- 新增服务能力：`sw.js` 与 `offline.html` 路由支持，PWA / 离线可用性增强。
- API 侧新增文件夹项增删改与目标目录删除流程，支持更细粒度目录维护。
- 建议现有 `2.3` 用户升级到 `2.4`。

## 支持与贡献

- Issues: https://github.com/leduchuong48-byte/tikplayer/issues
- Discussions: https://github.com/leduchuong48-byte/tikplayer/discussions

## 免责声明

使用本项目即表示你已阅读并同意 [DISCLAIMER.md](DISCLAIMER.md)。
