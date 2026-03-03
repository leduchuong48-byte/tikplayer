# TikPlayer

![TikPlayer UI](https://raw.githubusercontent.com/leduchuong48-byte/tikplayer/main/images/ui/desktop.png)

[![Docker Pulls](https://img.shields.io/docker/pulls/leduchuong/tikplayer?logo=docker&label=Docker%20Pulls)](https://hub.docker.com/r/leduchuong/tikplayer)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/leduchuong48-byte/tikplayer/blob/main/LICENSE)
[![Build: Passing](https://img.shields.io/badge/Build-Passing-brightgreen.svg)](#)
[![Platform: ARM64/AMD64](https://img.shields.io/badge/Platform-ARM64%2FAMD64-blue.svg)](#)

[中文](https://github.com/leduchuong48-byte/tikplayer/blob/main/README.md)

> Better alternative to web-file-player for E-ink devices.

TikPlayer is a lightweight NAS/HomeLab media player service focused on simple deployment, hardware-friendly playback, and easy remote access.

## Release Notes

- `v2.2`: `reload` moved from a boolean lock to a queue with progress percent and stage states, with queue status API added.
- `v2.2`: Added per-source `random_enabled` to support browse-only sources, plus backend path-level dedup in random pool.
- `v2.2`: On `move/delete`, random-pool stale entries are actively pruned by backend + path scope to improve collection consistency.
- `v2.2`: Account management now uses explicit Edit/Delete actions with clearer failure feedback on delete.
- `v2.2`: Mobile UI updated for Safari/Chrome with a single sticky top bar, dynamic viewport, and safe-area adaptation.
- `v2.2`: Frontend cache strategy fixed: `/` now returns `no-store` to avoid stale page assets.

## Why this tool?

Many self-hosted users need a quick media player stack that just works, but deployment and compatibility often become the bottleneck. TikPlayer keeps the workflow copy-paste friendly and reproducible.

## What the Project Does (Features)

- Web UI playback and basic media management
- Docker-first deployment for NAS/HomeLab
- Multi-arch support for ARM64 and AMD64

✅ Perfect for Raspberry Pi & Oracle Cloud Free Tier (ARM)

## UI Preview

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

## GitHub Topics (pick at least 5)

`#nas` `#homelab` `#selfhosted` `#synology` `#unraid` `#eink` `#automation`

## Where to Get Help

- Issues: `https://github.com/leduchuong48-byte/tikplayer/issues`

## Maintainer

- `@leduchuong48-byte`

## Disclaimer

By using this project, you acknowledge and agree to the [Disclaimer](https://github.com/leduchuong48-byte/tikplayer/blob/main/DISCLAIMER.md).

## License

MIT, see [LICENSE](https://github.com/leduchuong48-byte/tikplayer/blob/main/LICENSE).
