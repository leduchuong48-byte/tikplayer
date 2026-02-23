# TikPlayer

[中文](README.md)

A lightweight media browsing and playback service based on `FastAPI + AList + HLS`.

## Features

- Multi-source AList aggregation
- HLS and common video playback
- File browsing, search, rename, delete, create folder
- Quick-folder shortcuts
- Docker deployment

## Requirements

- Docker / Docker Compose (recommended)
- or Python `3.10+`

## Quick Start

```bash
docker compose up -d --build
```

Default URL: `http://localhost:1015`

## Security & Privacy

- Do not commit real credentials or tokens
- Keep `.env`, `data/token.key`, and `data/tokens.json` out of version control

## Disclaimer

By using this project, you acknowledge and agree to the [Disclaimer](DISCLAIMER.md).
