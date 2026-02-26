import os
import json
import random
import re
import time
import hashlib
import httpx
import asyncio
import urllib.parse
import subprocess
from typing import List, Dict, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from cryptography.fernet import Fernet, InvalidToken

# --- 数据模型 ---
class SourceModel(BaseModel):
    name: str
    url: str
    username: str = ""
    password: str = ""
    root_path: str = "/"
    selected_paths: List[str] = []


class SourceAuthModel(BaseModel):
    url: str
    username: str = ""
    password: str = ""


class SourceDirsModel(SourceAuthModel):
    path: str = "/"

class RenameModel(BaseModel):
    source: str
    path: str
    new_name: str

class MkdirModel(BaseModel):
    source: str
    path: str

# --- 全局变量 ---
DATA_DIR = "data"
CONFIG_FILE = os.path.join(DATA_DIR, "sources.json")
FOLDER_CONFIG_FILE = os.path.join(DATA_DIR, "folders.json")
TOKEN_STORE_FILE = os.path.join(DATA_DIR, "tokens.json")
TOKEN_KEY_FILE = os.path.join(DATA_DIR, "token.key")
alist_instances: Dict[str, dict] = {}
video_pool: List[Dict[str, str]] = []
scan_lock = asyncio.Lock()
transcode_semaphore = asyncio.Semaphore(3)  # 最多3个并发转码
token_cache: Dict[str, Dict[str, object]] = {}
persisted_tokens: Dict[str, str] = {}
token_cipher: Optional[Fernet] = None
shared_http_client: Optional[httpx.AsyncClient] = None

MEDIA_EXTENSIONS = {
    '.mp4', '.mkv', '.mov', '.avi', '.flv', '.webm', '.m3u8', '.ts', '.wmv',
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'
}
NATIVE_FORMATS = ('.mp4', '.webm', '.mov')

load_dotenv()


def _build_source_env_prefix(source_name: str, index: int) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", source_name).strip("_").upper()
    if safe_name:
        return f"ALIST_{safe_name}"
    return f"ALIST_SOURCE_{index + 1}"


def _apply_env_overrides(sources: List[dict]) -> List[dict]:
    if os.getenv("ALIST_ENV_OVERRIDE_ENABLED", "false").lower() not in {"1", "true", "yes", "on"}:
        return sources

    resolved_sources: List[dict] = []
    for idx, source in enumerate(sources):
        updated = dict(source)
        prefix = _build_source_env_prefix(str(source.get("name", "")), idx)
        indexed_prefix = f"ALIST_SOURCE_{idx + 1}"

        for field in ("url", "username", "password"):
            env_field = field.upper()
            env_value = os.getenv(f"{prefix}_{env_field}")
            if not env_value:
                env_value = os.getenv(f"{indexed_prefix}_{env_field}")
            if env_value:
                updated[field] = env_value

        resolved_sources.append(updated)

    return resolved_sources


def _token_cache_key(base_url: str, username: str, password: str) -> str:
    clean = base_url.rstrip('/').replace('/dav', '')
    raw = f"{clean}|{username}|{password}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_cached_token(base_url: str, username: str, password: str) -> Optional[str]:
    key = _token_cache_key(base_url, username, password)
    data = token_cache.get(key)
    if not data:
        return None
    raw_expires = data.get("expires_at")
    if isinstance(raw_expires, (int, float)):
        expires_at = float(raw_expires)
    else:
        expires_at = 0.0
    if time.time() >= expires_at:
        token_cache.pop(key, None)
        return None
    token = data.get("token")
    if isinstance(token, str) and token:
        return token
    return None


def _set_cached_token(base_url: str, username: str, password: str, token: str, ttl_seconds: int = 300) -> None:
    key = _token_cache_key(base_url, username, password)
    token_cache[key] = {
        "token": token,
        "expires_at": time.time() + ttl_seconds,
    }


def _clear_cached_token(base_url: str, username: str, password: str) -> None:
    key = _token_cache_key(base_url, username, password)
    token_cache.pop(key, None)


def _load_persisted_tokens() -> None:
    global persisted_tokens
    if not os.path.exists(TOKEN_STORE_FILE):
        persisted_tokens = {}
        return
    try:
        with open(TOKEN_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        os.chmod(TOKEN_STORE_FILE, 0o600)
        if isinstance(data, dict):
            persisted_tokens = {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v}
        else:
            persisted_tokens = {}

        # 兼容历史明文 token，加载后自动迁移为密文
        if token_cipher:
            needs_rewrite = False
            migrated: Dict[str, str] = {}
            for k, v in persisted_tokens.items():
                decrypted = _decrypt_token(v)
                if decrypted and v != _encrypt_token(decrypted):
                    needs_rewrite = True
                if decrypted:
                    migrated[k] = _encrypt_token(decrypted)
            if needs_rewrite:
                persisted_tokens = migrated
                _save_persisted_tokens()
    except Exception as e:
        print(f"Error: {e}")
        persisted_tokens = {}


def _save_persisted_tokens() -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(TOKEN_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(persisted_tokens, f, indent=2, ensure_ascii=False)
        os.chmod(TOKEN_STORE_FILE, 0o600)
    except Exception as e:
        print(f"Error: {e}")


def _get_persisted_token(base_url: str, username: str, password: str) -> Optional[str]:
    key = _token_cache_key(base_url, username, password)
    token = persisted_tokens.get(key)
    if not token:
        return None
    return _decrypt_token(token)


def _set_persisted_token(base_url: str, username: str, password: str, token: str) -> None:
    key = _token_cache_key(base_url, username, password)
    persisted_tokens[key] = _encrypt_token(token)
    _save_persisted_tokens()


def _clear_persisted_token(base_url: str, username: str, password: str) -> None:
    key = _token_cache_key(base_url, username, password)
    if key in persisted_tokens:
        persisted_tokens.pop(key, None)
        _save_persisted_tokens()


def _load_or_create_token_cipher() -> None:
    global token_cipher
    os.makedirs(DATA_DIR, exist_ok=True)

    env_key = (os.getenv("ALIST_TOKEN_ENC_KEY") or "").strip()
    if env_key:
        try:
            token_cipher = Fernet(env_key.encode("utf-8"))
            return
        except Exception as e:
            print(f"Error: invalid ALIST_TOKEN_ENC_KEY - {e}")

    try:
        if os.path.exists(TOKEN_KEY_FILE):
            with open(TOKEN_KEY_FILE, "rb") as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key()
            with open(TOKEN_KEY_FILE, "wb") as f:
                f.write(key)
            os.chmod(TOKEN_KEY_FILE, 0o600)

        token_cipher = Fernet(key)
        if os.path.exists(TOKEN_KEY_FILE):
            os.chmod(TOKEN_KEY_FILE, 0o600)
    except Exception as e:
        print(f"Error: token key init failed - {e}")
        token_cipher = None


def _encrypt_token(token: str) -> str:
    if not token_cipher:
        return token
    return token_cipher.encrypt(token.encode("utf-8")).decode("utf-8")


def _decrypt_token(token_text: str) -> Optional[str]:
    if not token_text:
        return None
    if not token_cipher:
        return token_text
    try:
        return token_cipher.decrypt(token_text.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # 历史明文 JWT 兼容
        if token_text.count(".") == 2:
            return token_text
        return None

# --- Alist 工具类 ---
class AlistHelper:
    @staticmethod
    def get_headers(token: str = ""):
        return {
            "Authorization": token,
            "Content-Type": "application/json",
            "User-Agent": "DeerPlayer/Pro"
        }

    @staticmethod
    async def login_with_error(client: httpx.AsyncClient, base_url: str, username: str, password: str) -> tuple[Optional[str], Optional[str]]:
        base_url = base_url.rstrip('/')
        if base_url.endswith('/dav'): base_url = base_url[:-4]
        url = f"{base_url}/api/auth/login"
        payload = {"username": username, "password": password}
        try:
            resp = await client.post(url, json=payload, headers=AlistHelper.get_headers(), timeout=15.0)
            data = resp.json()
            if resp.status_code == 200 and data.get('code') == 200:
                token = data.get('data', {}).get('token')
                if token:
                    return token, None
            return None, data.get('message') or f"HTTP {resp.status_code}"
        except Exception as e:
            print(f"Error: {e}")
            return None, str(e)

    @staticmethod
    async def login(client: httpx.AsyncClient, base_url: str, username: str, password: str) -> Optional[str]:
        token, _ = await AlistHelper.login_with_error(client, base_url, username, password)
        return token

    @staticmethod
    async def validate_token(client: httpx.AsyncClient, base_url: str, token: str) -> bool:
        clean = base_url.rstrip('/')
        if clean.endswith('/dav'):
            clean = clean[:-4]
        url = f"{clean}/api/me"
        try:
            resp = await client.get(url, headers=AlistHelper.get_headers(token), timeout=10.0)
            if resp.status_code != 200:
                return False
            data = resp.json()
            return data.get("code") == 200
        except Exception as e:
            print(f"Error: {e}")
            return False
    @staticmethod
    async def list_files_with_error(client: httpx.AsyncClient, base_url: str, token: str, path: str) -> tuple[List[dict], Optional[str]]:
        base_url = base_url.rstrip('/').replace('/dav', '')
        url = f"{base_url}/api/fs/list"
        payload = {"path": path, "password": "", "page": 1, "per_page": 0, "refresh": False}
        try:
            resp = await client.post(url, headers=AlistHelper.get_headers(token), json=payload, timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 200:
                    return data['data']['content'] or [], None
                return [], data.get('message') or 'fs/list failed'
            return [], f"HTTP {resp.status_code}"
        except Exception as e:
            print(f"Error: {e}")
            return [], str(e)

    @staticmethod
    async def list_files(client: httpx.AsyncClient, base_url: str, token: str, path: str) -> List[dict]:
        files, _ = await AlistHelper.list_files_with_error(client, base_url, token, path)
        return files

    @staticmethod
    async def get_file_details_with_error(client: httpx.AsyncClient, base_url: str, token: str, path: str) -> tuple[Optional[dict], Optional[str]]:
        base_url = base_url.rstrip('/').replace('/dav', '')
        url = f"{base_url}/api/fs/get"
        payload = {"path": path, "password": ""}
        try:
            resp = await client.post(url, headers=AlistHelper.get_headers(token), json=payload, timeout=15.0)
            data = resp.json()
            if data.get('code') == 200:
                return data['data'], None
            return None, data.get('message') or 'fs/get failed'
        except Exception as e:
            print(f"Error: {e}")
            return None, str(e)

    @staticmethod
    async def get_file_details(base_url: str, token: str, path: str):
        client = shared_http_client or httpx.AsyncClient()
        try:
            details, _ = await AlistHelper.get_file_details_with_error(client, base_url, token, path)
            return details
        finally:
            if client is not shared_http_client:
                await client.aclose()

    @staticmethod
    async def delete_file(base_url: str, token: str, full_path: str) -> tuple[bool, str]:
        base_url = base_url.rstrip('/').replace('/dav', '')
        url = f"{base_url}/api/fs/remove"
        dir_path, file_name = os.path.split(full_path)
        if not dir_path: dir_path = "/"
        payload = {"dir": dir_path, "names": [file_name]}
        try:
            client = shared_http_client or httpx.AsyncClient()
            resp = await client.post(url, headers=AlistHelper.get_headers(token), json=payload, timeout=15.0)
            data = resp.json()
            if data.get('code') == 200: return True, "Success"
            else: return False, data.get('message', 'Unknown Error')
        except Exception as e: return False, str(e)


async def get_source_token(
    client: httpx.AsyncClient,
    base_url: str,
    username: str,
    password: str,
    force_refresh: bool = False,
    verify_cached: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    if not force_refresh:
        cached = _get_cached_token(base_url, username, password)
        if cached:
            if not verify_cached or await AlistHelper.validate_token(client, base_url, cached):
                return cached, None
            _clear_cached_token(base_url, username, password)

        persisted = _get_persisted_token(base_url, username, password)
        if persisted:
            if not verify_cached or await AlistHelper.validate_token(client, base_url, persisted):
                _set_cached_token(base_url, username, password, persisted)
                return persisted, None
            _clear_persisted_token(base_url, username, password)

    token, err = await AlistHelper.login_with_error(client, base_url, username, password)
    if token:
        _set_cached_token(base_url, username, password, token)
        _set_persisted_token(base_url, username, password, token)
        return token, None

    return None, err

# --- FFmpeg ---
def _parse_transcode_backends() -> List[str]:
    raw = (os.getenv("TRANSCODE_BACKENDS") or "qsv,vaapi,cpu").strip().lower()
    allowed = {"qsv", "vaapi", "cpu"}
    result: List[str] = []
    for item in [x.strip() for x in raw.split(",") if x.strip()]:
        if item in allowed and item not in result:
            result.append(item)
    return result or ["qsv", "vaapi", "cpu"]


def _build_ffmpeg_cmd(input_url: str, backend: str) -> List[str]:
    common_input = [
        "ffmpeg",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_on_network_error", "1",
        "-reconnect_on_http_error", "4xx,5xx",
        "-reconnect_delay_max", "5",
        "-rw_timeout", "15000000",
        "-i", input_url,
    ]
    common_audio = ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
    common_output = ["-f", "mp4", "-movflags", "frag_keyframe+empty_moov", "pipe:1"]

    if backend == "qsv":
        return common_input + [
            "-c:v", "h264_qsv",
            "-preset", "veryfast",
            "-b:v", "2500k",
            "-maxrate", "3000k",
            "-bufsize", "6000k",
        ] + common_audio + common_output

    if backend == "vaapi":
        return ["ffmpeg", "-vaapi_device", "/dev/dri/renderD128", "-i", input_url] + [
            "-vf", "format=nv12,hwupload",
            "-c:v", "h264_vaapi",
            "-b:v", "2500k",
            "-maxrate", "3000k",
            "-bufsize", "6000k",
        ] + common_audio + common_output

    # CPU fallback
    return common_input + [
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-b:v", "2500k",
        "-maxrate", "3000k",
        "-bufsize", "6000k",
    ] + common_audio + common_output


def _cleanup_process(process):
    """安全清理 FFmpeg 子进程：kill → wait → 关闭管道"""
    try:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    except Exception:
        pass
    for pipe in (process.stdout, process.stderr, process.stdin):
        if pipe:
            try: pipe.close()
            except Exception: pass


def ffmpeg_transcode_generator(input_url: str):
    backends = _parse_transcode_backends()
    last_error = ""

    for backend in backends:
        cmd = _build_ffmpeg_cmd(input_url, backend)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**7)
        try:
            first_chunk = process.stdout.read(32768) if process.stdout else b""
            if first_chunk:
                print(f"✅ Transcode backend in use: {backend}")
                yield first_chunk
                while True:
                    chunk = process.stdout.read(32768) if process.stdout else b""
                    if not chunk:
                        break
                    yield chunk
                return

            if process.poll() is None:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    retry_chunk = process.stdout.read(32768) if process.stdout else b""
                    if retry_chunk:
                        print(f"✅ Transcode backend in use: {backend}")
                        yield retry_chunk
                        while True:
                            chunk = process.stdout.read(32768) if process.stdout else b""
                            if not chunk:
                                break
                            yield chunk
                        return

            # 读 stderr 时加超时保护，防止阻塞
            err = b""
            if process.stderr:
                import selectors
                sel = selectors.DefaultSelector()
                sel.register(process.stderr, selectors.EVENT_READ)
                ready = sel.select(timeout=3)
                if ready:
                    err = process.stderr.read()
                sel.close()
            last_error = err.decode("utf-8", errors="ignore")[:500]
            print(f"⚠️ Transcode backend failed: {backend} | {last_error}")
        finally:
            _cleanup_process(process)

    raise RuntimeError(f"All transcode backends failed. Last error: {last_error or 'unknown error'}")

# --- Logic ---
def _migrate_legacy_configs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    legacy_sources = "sources.json"
    legacy_folders = "folders.json"

    if not os.path.exists(CONFIG_FILE) and os.path.exists(legacy_sources):
        try:
            with open(legacy_sources, 'r', encoding='utf-8') as src_f:
                sources = json.load(src_f)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as dst_f:
                json.dump(sources, dst_f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error: {e}")

    if not os.path.exists(FOLDER_CONFIG_FILE) and os.path.exists(legacy_folders):
        try:
            with open(legacy_folders, 'r', encoding='utf-8') as src_f:
                folders = json.load(src_f)
            with open(FOLDER_CONFIG_FILE, 'w', encoding='utf-8') as dst_f:
                json.dump(folders, dst_f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error: {e}")


def load_config() -> List[dict]:
    _migrate_legacy_configs()
    if not os.path.exists(CONFIG_FILE): return []
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            sources = json.load(f)
        return _apply_env_overrides(sources)
    except Exception as e:
        print(f"Error: {e}")
        return []

def save_config(sources: List[dict]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(sources, f, indent=2, ensure_ascii=False)

async def deep_scan_alist(client: httpx.AsyncClient, base_url: str, token: str, root_path: str, source_name: str) -> List[dict]:
    results = []
    if not root_path: root_path = "/"
    queue = [root_path]
    clean_base_url = base_url.rstrip('/').replace('/dav', '')
    
    while queue:
        current_path = queue.pop(0)
        files = await AlistHelper.list_files(client, clean_base_url, token, current_path)
        for item in files:
            full_path = os.path.join(current_path, item['name']).replace('\\', '/')
            if item['is_dir']:
                queue.append(full_path)
            else:
                ext = os.path.splitext(item['name'])[1].lower()
                if ext in MEDIA_EXTENSIONS:
                    is_img = ext in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
                    results.append({
                        "source": source_name, "path": full_path, 
                        "thumb": item.get('thumb', ''), "type": "image" if is_img else "video"
                    })
    return results

async def reload_system_async():
    global alist_instances, video_pool
    if scan_lock.locked(): return
    async with scan_lock:
        sources = load_config()
        new_instances = {}
        new_video_pool = []
        async with httpx.AsyncClient() as client:
            for src in sources:
                name = src['name']
                url = src['url']
                username = src.get('username') or ""
                password = src.get('password') or ""
                token, login_err = await get_source_token(client, url, username, password, verify_cached=True)
                if token:
                    new_instances[name] = {"token": token, "url": url, "conf": src}
                    selected_paths = src.get('selected_paths') or [src.get('root_path', '/')]
                    print(f"📂 扫描源 '{name}' 的选定路径: {selected_paths}")
                    for root in selected_paths:
                        videos = await deep_scan_alist(client, url, token, root, name)
                        new_video_pool.extend(videos)
                    print(f"   └─ 源 '{name}' 共扫描到 {len(new_video_pool)} 个媒体文件")
                elif login_err:
                    print(f"Reload login failed for source '{name}': {login_err}")

        alist_instances = new_instances

        if new_video_pool:
            random.shuffle(new_video_pool)
            video_pool = new_video_pool
        elif not sources:
            video_pool = []
        else:
            video_pool = []

# --- API ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global shared_http_client
    os.makedirs("image", exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    _load_or_create_token_cipher()
    _load_persisted_tokens()
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("✅ FFmpeg detected")
    except Exception as e:
        print("⚠️ FFmpeg missing")
        print(f"Error: {e}")
    shared_http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=30.0),
        timeout=httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=5.0),
        follow_redirects=True,
    )
    asyncio.create_task(reload_system_async())
    yield
    if shared_http_client is not None:
        await shared_http_client.aclose()
        shared_http_client = None

app = FastAPI(lifespan=lifespan)
os.makedirs("image", exist_ok=True)
app.mount("/image", StaticFiles(directory="image"), name="image")
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def read_index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f: return HTMLResponse(content=f.read())
    return HTMLResponse("index.html missing")

@app.get("/manifest.json")
async def get_manifest():
    if os.path.exists("manifest.json"):
        return FileResponse("manifest.json", media_type="application/manifest+json")
    raise HTTPException(status_code=404)

# --- Source Config API ---
@app.get("/v1/sources")
async def get_sources(): return load_config()

@app.post("/v1/sources")
async def add_source(source: SourceModel):
    current = load_config()
    # 检查是否存在，存在则更新，不存在则添加
    existing = next((i for i, s in enumerate(current) if s['name'] == source.name), None)
    if existing is not None:
        current[existing] = source.dict()
    else:
        current.append(source.dict())
    save_config(current)
    asyncio.create_task(reload_system_async())
    return {"status": "success", "message": "已保存并自动刷新"}


@app.post("/v1/source/test-login")
async def test_source_login(payload: SourceAuthModel):
    async with httpx.AsyncClient() as client:
        token, login_err = await get_source_token(client, payload.url, payload.username, payload.password, force_refresh=True)
    if not token:
        raise HTTPException(status_code=400, detail=login_err or "Login failed")
    return {"status": "success"}


@app.post("/v1/source/dirs")
async def browse_source_dirs(payload: SourceDirsModel):
    username = payload.username or ""
    password = payload.password or ""
    async with httpx.AsyncClient() as client:
        token, login_err = await get_source_token(client, payload.url, username, password)
        if not token:
            raise HTTPException(status_code=400, detail=login_err or "Login failed")

        files, err = await AlistHelper.list_files_with_error(client, payload.url, token, payload.path or "/")
        if err and "token is invalidated" in err.lower():
            token, login_err = await get_source_token(client, payload.url, username, password, force_refresh=True)
            if not token:
                raise HTTPException(status_code=400, detail=login_err or "Login failed")
            files, err = await AlistHelper.list_files_with_error(client, payload.url, token, payload.path or "/")
        if err:
            raise HTTPException(status_code=502, detail=err)

    return [
        {
            "name": item.get("name", ""),
            "path": os.path.join(payload.path or "/", item.get("name", "")).replace("\\", "/"),
            "is_dir": bool(item.get("is_dir", False)),
        }
        for item in files
        if item.get("is_dir")
    ]

@app.post("/v1/reload")
async def reload_sources():
    """手动触发源配置刷新"""
    try:
        asyncio.create_task(reload_system_async())
        return {"status": "success", "message": "Reload triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/reload/status")
async def get_reload_status():
    """获取当前刷新状态"""
    return {
        "is_refreshing": scan_lock.locked(),
        "sources_count": len(alist_instances),
        "video_pool_size": len(video_pool)
    }


@app.delete("/v1/sources/{name}")
async def remove_source(name: str):
    current = load_config()
    current = [s for s in current if s['name'] != name]
    save_config(current)
    asyncio.create_task(reload_system_async())
    return {"status": "success", "message": "已删除并自动刷新"}

# --- Folder Config API ---
@app.get("/v1/folders")
async def get_folders():
    _migrate_legacy_configs()
    if not os.path.exists(FOLDER_CONFIG_FILE):
        return []
    try:
        with open(FOLDER_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error: {e}")
        return []

@app.post("/v1/folders")
async def save_folders(folders: List[dict]):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(FOLDER_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(folders, f, indent=2, ensure_ascii=False)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Media API ---
@app.get("/v1/get_video")
async def get_random_video(request: Request):
    if not video_pool:
        if not scan_lock.locked(): asyncio.create_task(reload_system_async())
        raise HTTPException(status_code=503, detail="Initializing")
    media = random.choice(video_pool)
    return build_media_response(request, media)

def build_media_response(request: Request, media: dict):
    encoded_path = urllib.parse.quote(media['path'])
    stream_url = f"{request.base_url}v1/stream?source={media['source']}&path={encoded_path}"
    transcode_url = f"{request.base_url}v1/transcode?source={media['source']}&path={encoded_path}"
    download_url = f"{request.base_url}v1/download?source={media['source']}&path={encoded_path}"
    is_native = media['path'].lower().endswith(NATIVE_FORMATS)
    return {
        "url": stream_url, "transcode_url": transcode_url, "download_url": download_url,
        "source": media['source'], "raw_path": media['path'], "img_url": media.get('thumb') or "/image/no_preview.png",
        "type": media.get('type', 'video'), "recommend_transcode": not is_native,
        "name": os.path.basename(media['path'])
    }


async def _resolve_media_raw_url(source: str, path: str) -> str:
    if source not in alist_instances:
        raise HTTPException(status_code=404, detail="Source not found")

    if shared_http_client is None:
        raise HTTPException(status_code=503, detail="HTTP client not initialized")

    instance = alist_instances[source]
    clean_url = instance['url'].rstrip('/').replace('/dav', '')
    conf = instance.get('conf', {})
    username = str(conf.get('username') or "")
    password = str(conf.get('password') or "")

    details, err = await AlistHelper.get_file_details_with_error(shared_http_client, clean_url, instance['token'], path)
    if err and "token is invalidated" in err.lower():
        token, login_err = await get_source_token(shared_http_client, clean_url, username, password, force_refresh=True)
        if not token:
            raise HTTPException(status_code=400, detail=login_err or "Login failed")
        instance['token'] = token
        details, err = await AlistHelper.get_file_details_with_error(shared_http_client, clean_url, token, path)

    if err:
        raise HTTPException(status_code=502, detail=err)
    if not details or not details.get('raw_url'):
        raise HTTPException(status_code=404, detail="File unavailable")
    return str(details.get('raw_url'))

@app.get("/v1/stream")
async def stream_video(source: str, path: str):
    raw_url = await _resolve_media_raw_url(source, path)
    return RedirectResponse(url=raw_url, status_code=302)

@app.get("/v1/transcode")
async def transcode_video(source: str, path: str):
    raw_url = await _resolve_media_raw_url(source, path)
    acquired = transcode_semaphore._value > 0  # 检查是否有空位
    if not acquired and transcode_semaphore._value <= 0:
        raise HTTPException(status_code=503, detail="转码队列已满，请稍后重试")
    await transcode_semaphore.acquire()
    def guarded_generator():
        try:
            yield from ffmpeg_transcode_generator(raw_url)
        finally:
            transcode_semaphore.release()
    return StreamingResponse(guarded_generator(), media_type="video/mp4")

@app.get("/v1/download")
async def download_video(source: str, path: str):
    raw_url = await _resolve_media_raw_url(source, path)
    async def iterfile():
        if shared_http_client is None:
            raise HTTPException(status_code=503, detail="HTTP client not initialized")
        async with shared_http_client.stream("GET", raw_url, follow_redirects=True) as r:
            async for chunk in r.aiter_bytes():
                yield chunk
    file_name = os.path.basename(path)
    return StreamingResponse(iterfile(), headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(file_name)}"}, media_type="application/octet-stream")

# --- File System Operations (Move, Delete, Rename, Mkdir) ---

@app.post("/v1/delete_video")
async def delete_video(payload: dict):
    source_name = payload.get("source")
    file_path = payload.get("path")
    if not isinstance(file_path, str) or not file_path:
        raise HTTPException(status_code=400)
    if source_name not in alist_instances: raise HTTPException(status_code=404)
    instance = alist_instances[source_name]
    conf = instance.get('conf', {})
    token = instance['token']

    # 带重试的删除（处理 SMB 共享锁 STATUS_SHARING_VIOLATION）
    max_retries = 3
    for attempt in range(max_retries):
        success, msg = await AlistHelper.delete_file(instance['url'], token, file_path)
        if success:
            break
        # token 过期 → 刷新后重试
        if 'token' in msg.lower():
            new_token, _ = await get_source_token(
                shared_http_client, instance['url'].rstrip('/').replace('/dav', ''),
                str(conf.get('username') or ''), str(conf.get('password') or ''), force_refresh=True)
            if new_token:
                token = new_token
                instance['token'] = token
                continue
        # SMB 共享锁 → 等待后重试（文件句柄可能还未释放）
        if 'sharing' in msg.lower() or 'share access' in msg.lower() or 'incompatible' in msg.lower():
            if attempt < max_retries - 1:
                await asyncio.sleep(1 * (2 ** attempt))  # 指数退避: 1s, 2s, 4s
                continue
        break

    if success:
        global video_pool
        video_pool = [v for v in video_pool if not (v['source'] == source_name and v['path'] == file_path)]
        return {"status": "success"}
    else: raise HTTPException(status_code=500, detail=msg)

@app.post("/v1/move_video")
async def move_video(payload: dict):
    source_name, src_path, dst_dir = payload.get("source"), payload.get("src_path"), payload.get("dst_dir")
    if not all([source_name, src_path, dst_dir]): raise HTTPException(status_code=400)
    src_path = str(src_path)
    dst_dir = str(dst_dir)
    if source_name not in alist_instances: raise HTTPException(status_code=404)
    instance = alist_instances[source_name]
    conf = instance.get('conf', {})
    base_url = instance['url'].rstrip('/').replace('/dav', '')
    src_dir, file_name = os.path.split(src_path)
    api_url = f"{base_url}/api/fs/move"
    body = {"src_dir": src_dir or "/", "dst_dir": dst_dir, "names": [file_name]}

    async def _do_move(token: str) -> dict:
        client = shared_http_client or httpx.AsyncClient()
        resp = await client.post(api_url, headers=AlistHelper.get_headers(token), json=body, timeout=15.0)
        return resp.json()

    # 带重试的移动（处理 token 过期和 SMB 共享锁）
    max_retries = 3
    last_msg = ''
    token = instance['token']
    for attempt in range(max_retries):
        try:
            data = await _do_move(token)
        except Exception as e:
            last_msg = str(e)
            break
        if data.get('code') == 200:
            global video_pool
            video_pool = [v for v in video_pool if not (v['source'] == source_name and v['path'] == src_path)]
            return {"status": "success"}
        last_msg = str(data.get('message', ''))
        # token 过期 → 刷新后重试
        if 'token' in last_msg.lower():
            new_token, _ = await get_source_token(
                shared_http_client, base_url,
                str(conf.get('username') or ''), str(conf.get('password') or ''), force_refresh=True)
            if new_token:
                token = new_token
                instance['token'] = token
                continue
        # SMB 共享锁 → 指数退避重试
        if 'sharing' in last_msg.lower() or 'share access' in last_msg.lower() or 'incompatible' in last_msg.lower():
            if attempt < max_retries - 1:
                await asyncio.sleep(1 * (2 ** attempt))  # 指数退避: 1s, 2s, 4s
                continue
        break
    raise HTTPException(status_code=500, detail=last_msg)

@app.post("/v1/fs/rename")
async def rename_file(payload: RenameModel):
    if payload.source not in alist_instances: raise HTTPException(status_code=404)
    instance = alist_instances[payload.source]
    base_url = instance['url'].rstrip('/').replace('/dav', '')
    url = f"{base_url}/api/fs/rename"
    body = {"name": payload.new_name, "path": payload.path}
    try:
        client = shared_http_client or httpx.AsyncClient()
        resp = await client.post(url, headers=AlistHelper.get_headers(instance['token']), json=body, timeout=15.0)
        data = resp.json()
        if data.get('code') == 200: return {"status": "success"}
        else: raise HTTPException(status_code=500, detail=data.get('message'))
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/fs/mkdir")
async def make_directory(payload: MkdirModel):
    if payload.source not in alist_instances: raise HTTPException(status_code=404)
    instance = alist_instances[payload.source]
    base_url = instance['url'].rstrip('/').replace('/dav', '')
    url = f"{base_url}/api/fs/mkdir"
    body = {"path": payload.path}
    try:
        client = shared_http_client or httpx.AsyncClient()
        resp = await client.post(url, headers=AlistHelper.get_headers(instance['token']), json=body, timeout=15.0)
        data = resp.json()
        if data.get('code') == 200: return {"status": "success"}
        else: raise HTTPException(status_code=500, detail=data.get('message'))
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/browse")
async def browse_directory(source: str, path: str, unfiltered: bool = False):
    if source not in alist_instances: raise HTTPException(status_code=404, detail="Source not found")
    instance = alist_instances[source]
    clean_url = instance['url'].rstrip('/').replace('/dav', '')
    conf = instance.get('conf', {})
    username = str(conf.get('username') or "")
    password = str(conf.get('password') or "")
    async with httpx.AsyncClient() as client:
        files, err = await AlistHelper.list_files_with_error(client, clean_url, instance['token'], path)
        if err and "token is invalidated" in err.lower():
            token, login_err = await get_source_token(client, clean_url, username, password, force_refresh=True)
            if token:
                instance['token'] = token
                files, err = await AlistHelper.list_files_with_error(client, clean_url, token, path)
            elif login_err:
                raise HTTPException(status_code=400, detail=login_err)
    if err:
        raise HTTPException(status_code=502, detail=err)
    # 获取该源的 selected_paths，用于过滤浏览结果
    selected_paths = conf.get('selected_paths') or [conf.get('root_path', '/')]
    norm_selected = [sp.rstrip('/') or '/' for sp in selected_paths]

    def is_path_allowed(item_path: str, is_dir: bool) -> bool:
        """检查路径是否在 selected_paths 范围内（或是其祖先目录）"""
        np = item_path.rstrip('/') or '/'
        for sp in norm_selected:
            # 文件/目录在选定路径内部
            if np == sp or np.startswith(sp + '/'):
                return True
            # 目录是选定路径的祖先（允许导航到选定路径）
            if is_dir and sp.startswith(np + '/'):
                return True
        return False

    result = []
    for item in files:
        is_dir = item['is_dir']
        ext = os.path.splitext(item['name'])[1].lower()
        if not (is_dir or ext in MEDIA_EXTENSIONS):
            continue
        item_path = os.path.join(path, item['name']).replace('\\', '/')
        if not unfiltered and not is_path_allowed(item_path, is_dir):
            continue
        result.append({
            "name": item['name'],
            "path": item_path,
            "is_dir": is_dir,
            "thumb": item.get('thumb', ''),
            "size": item.get('size', 0),
            "type": "folder" if is_dir else ("image" if ext in {'.jpg', '.jpeg', '.png', '.gif', '.webp'} else "video")
        })
    return result
