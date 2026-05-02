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

Tikplayer is a lightweight self-hosted media browsing and playback web app for NAS / HomeLab environments, with multi-source browsing, playback controls, and quick organize actions.

## Interface

### Web UI (2.4)

> Screenshots below are captured from an isolated demo instance.

![Home](https://raw.githubusercontent.com/leduchuong48-byte/tikplayer/main/docs/ui/home-v24.png)
![Files](https://raw.githubusercontent.com/leduchuong48-byte/tikplayer/main/docs/ui/files-v24.png)
![Profile](https://raw.githubusercontent.com/leduchuong48-byte/tikplayer/main/docs/ui/profile-v24.png)

## Support Matrix

| Category | Support |
|---|---|
| Runtime | FastAPI + Web UI |
| Core Use Cases | playback, browsing, quick organize, basic file actions |
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
- Production recommendation: enable auth and SSRF host restrictions.

## Upgrade Notes (2.4 vs 2.3)

- Version bump aligned to `2.4` across Dockerfile and UI labels.
- UI navigation and directory back action improved.
- Folder config model enhanced with ID/status/sort/note/last-used fields.
- Added `sw.js` and `offline.html` routes for better PWA/offline behavior.
- Added folder item CRUD and target-folder delete API flow for finer management.
- Upgrade from `2.3` to `2.4` is recommended.

## Support & Contribution

- Issues: https://github.com/leduchuong48-byte/tikplayer/issues
- Discussions: https://github.com/leduchuong48-byte/tikplayer/discussions

## Disclaimer

By using this project, you agree to [DISCLAIMER.md](DISCLAIMER.md).
