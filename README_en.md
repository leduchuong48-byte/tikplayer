<h1 align="center">Tikplayer</h1>

<p align="center">
<a href="https://github.com/leduchuong48-byte/tikplayer/releases"><img alt="Release" src="https://img.shields.io/github/v/release/leduchuong48-byte/tikplayer?display_name=tag"></a>
<a href="https://hub.docker.com/r/leduchuong/tikplayer"><img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/leduchuong/tikplayer?logo=docker"></a>
<a href="https://github.com/leduchuong48-byte/tikplayer/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/leduchuong48-byte/tikplayer"></a>
<a href="https://github.com/leduchuong48-byte/tikplayer/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/leduchuong48-byte/tikplayer"></a>
</p>

<h3 align="center">
  <a href="README.md">中文</a><span> · </span>
  <a href="https://github.com/leduchuong48-byte/tikplayer/issues">Report Bug</a>
  <span> · </span>
  <a href="https://github.com/leduchuong48-byte/tikplayer/discussions">Discussions</a>
</h3>

## Overview

Tikplayer is a lightweight self-hosted media browser/player for NAS and HomeLab use cases.

## Interface

### Web UI (2.4)

> Screenshots are intentionally removed due to privacy requirements.
> Please preview UI only in an isolated local demo environment.

## Support Matrix

| Category | Support |
|---|---|
| Runtime | FastAPI + Web UI |
| Core Use Cases | playback, browsing, quick organize, file actions |
| Deployment | Docker / Docker Compose / N97 |

## Installation

```bash
git clone https://github.com/leduchuong48-byte/tikplayer.git
cd tikplayer
cp .env.example .env
```

## Docker

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

## Configuration

- Core files: `sources.json`, `folders.json`
- Runtime env: `.env`
- Production recommendation: enable auth and host restrictions.

## Upgrade Notes (2.4 vs 2.3)

- Version markers aligned to `2.4`.
- Improved Web UI navigation and folder-back interaction.
- Enhanced folder config model with stable ID/status/sort/note/last-used fields.
- Added `sw.js` and `offline.html` routes for better PWA/offline behavior.
- Added folder item CRUD and target-folder delete APIs.
- Upgrade from `2.3` to `2.4` is recommended.

## Support & Contribution

- Issues: https://github.com/leduchuong48-byte/tikplayer/issues
- Discussions: https://github.com/leduchuong48-byte/tikplayer/discussions

## Disclaimer

By using this project, you agree to [DISCLAIMER.md](DISCLAIMER.md).
