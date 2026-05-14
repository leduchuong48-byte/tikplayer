# Tikplayer 2.4

![Tikplayer UI Preview](docs/reviewed-ui/approved-01-review-01-entry-39.png)

[![Docker Pulls](https://img.shields.io/docker/pulls/leduchuong/tikplayer?logo=docker&label=Docker%20Pulls&style=flat-square)](https://hub.docker.com/r/leduchuong/tikplayer)
[![GitHub Stars](https://img.shields.io/github/stars/leduchuong48-byte/tikplayer?style=flat-square)](https://github.com/leduchuong48-byte/tikplayer/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/leduchuong48-byte/tikplayer?style=flat-square)](https://github.com/leduchuong48-byte/tikplayer/network/members)
[![GitHub Issues](https://img.shields.io/github/issues/leduchuong48-byte/tikplayer?style=flat-square)](https://github.com/leduchuong48-byte/tikplayer/issues)
[![Platform: AMD64](https://img.shields.io/badge/Platform-AMD64-blue.svg)](#)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](#)

[中文](README.md)

> A web UI for AList media browsing, playback, and file actions.

Tikplayer 2.4 is a web interface for browsing, playing, downloading, and organizing media from AList sources in NAS and other self-hosted environments.

## Why this tool?

Generic file browsers are usually organized around file management rather than media playback. Tikplayer keeps source refresh, random play, folder play, download, move, delete, and fallback transcoding in one web UI.

## Highlights in 2.4

- AList-based media browsing and playback
- Main screen actions for refresh, fullscreen, download, mute, rotate, archive, and delete
- File workspace with source switching, folder browsing, search, and folder play
- Settings workspace for account management, path picking, and quick archive targets
- Direct playback with fallback transcoding through `qsv`, `vaapi`, and `cpu` backends
- The published container tags currently provide `linux/amd64` builds with Intel `/dev/dri` focused acceleration; build your own image for other architectures

## UI Preview

The screenshots below show the reviewed main work interfaces in plan order.

![UI Screenshot 1](docs/reviewed-ui/approved-01-review-01-entry-39.png)

![UI Screenshot 2](docs/reviewed-ui/approved-02-review-02-entry-43.png)

![UI Screenshot 3](docs/reviewed-ui/approved-03-review-03-entry-35.png)

## Quick Start

```bash
docker run --rm -p 1015:8000 leduchuong/tikplayer:latest
```

## Docker Compose

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
    devices:
      - /dev/dri:/dev/dri
    group_add:
      - "44"
      - "109"
    environment:
      - LIBVA_DRIVER_NAME=iHD
      - TRANSCODE_BACKENDS=qsv,vaapi,cpu
    volumes:
      - ./image:/app/image
      - ./data:/app/data
      - ./static:/app/static:ro
    shm_size: "2gb"
```

## Configuration

- The app listens on port `8000`; a common host mapping is `1015:8000`
- Configure your AList endpoint, credentials, and browse paths from the `My` page
- Keep `/dev/dri` mapped when you want `qsv` or `vaapi` hardware transcoding
- When no hardware backend is available, Tikplayer can fall back to `cpu` transcoding

## Core Capabilities

- AList source configuration, login, and path persistence
- Random play, folder play, media download, fullscreen, and rotate controls
- Quick archive targets plus rename, delete, and move actions
- Startup media reload flow with manual refresh and status endpoints
- PWA install prompt, offline page, and service worker support

## Suggested Topics

`#nas` `#homelab` `#selfhosted` `#alist` `#media-player` `#pwa` `#docker`

## Support

- Issues: https://github.com/leduchuong48-byte/tikplayer/issues
- Repository: https://github.com/leduchuong48-byte/tikplayer
- Docker Hub: https://hub.docker.com/r/leduchuong/tikplayer

## Disclaimer

By using this project you agree to the [disclaimer](DISCLAIMER.md). Only use it with media sources you are allowed to access and manage.
