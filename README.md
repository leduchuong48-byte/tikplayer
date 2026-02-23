# TikPlayer

基于 `FastAPI + AList + HLS` 的轻量媒体浏览与播放服务，支持从多个 AList 源聚合视频/图片并在网页端管理。

## 功能

- 多源 AList 配置与统一浏览
- 视频播放（HLS / 常见视频格式）
- 文件浏览、目录切换、搜索、重命名、删除、创建目录
- 快捷收纳槽位（快捷路径）
- Docker 一键部署

## 环境要求

- Docker / Docker Compose（推荐）
- 或 Python `3.10+`

## 快速开始

### 方式一：Docker Compose

```bash
docker compose up -d --build
```

默认访问：`http://localhost:1015`

### 方式二：本地运行

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 配置

1. 复制示例配置：

```bash
cp .env.example .env
```

2. 按需填写 `.env` 中的 AList 连接信息。
3. 如需固定加密密钥，可设置 `ALIST_TOKEN_ENC_KEY`。

## 目录说明

- `main.py`：后端 API 与业务逻辑
- `index.html`：前端页面
- `data/`：运行期数据（sources/folders/token）
- `image/`：静态资源

## 隐私与安全

- 仓库中不应提交真实账号、密码、令牌与私有地址。
- `.env`、`data/token.key`、`data/tokens.json` 已默认忽略。
- 发布前请执行一次敏感信息扫描。

## License

请按你的发布计划补充许可证（如 MIT）。
