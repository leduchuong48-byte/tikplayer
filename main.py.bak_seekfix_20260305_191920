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
from collections import deque
from typing import List, Dict, Optional
from contextlib import asynccontextmanager, suppress

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
    random_enabled: bool = True


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
stale_prune_task: Optional[asyncio.Task] = None
reload_state_lock = asyncio.Lock()
reload_worker_task: Optional[asyncio.Task] = None
reload_state: Dict[str, object] = {
    "is_refreshing": False,
    "queue_size": 0,
    "active_job_id": 0,
    "job_seq": 0,
    "progress_percent": 0.0,
    "progress_stage": "idle",
    "progress_detail": "",
    "progress_completed_units": 0,
    "progress_total_units": 0,
    "sources_total": 0,
    "sources_done": 0,
    "paths_total": 0,
    "paths_done": 0,
    "current_source": "",
    "current_path": "",
    "last_started_ts": None,
    "last_finished_ts": None,
    "last_duration_ms": 0.0,
    "last_result": "idle",
    "last_error": "",
    "last_reason": "",
    "total_requested": 0,
    "total_completed": 0,
    "total_failed": 0,
}

STREAM_EVENTS_MAX = 5000
stream_events = deque(maxlen=STREAM_EVENTS_MAX)
stream_counters: Dict[str, object] = {
    "resolve_attempts": 0,
    "resolve_success": 0,
    "resolve_fail": 0,
    "fail_reasons": {},
    "evicted_stale": 0,
    "last_prune": {
        "ts": None,
        "sample_size": 0,
        "checked": 0,
        "removed": 0,
        "skipped": 0,
    },
}

MEDIA_EXTENSIONS = {
    '.mp4', '.mkv', '.mov', '.avi', '.flv', '.webm', '.m3u8', '.ts', '.wmv',
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'
}
NATIVE_FORMATS = ('.mp4', '.webm', '.mov')
APP_NAME = "Tikplayer"
APP_VERSION = "2.2"

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


def _source_random_enabled(source_conf: dict) -> bool:
    raw = source_conf.get("random_enabled", True)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in {"0", "false", "no", "off"}:
            return False
        if lowered in {"1", "true", "yes", "on"}:
            return True
    return True


def _selected_paths_from_conf(source_conf: dict) -> List[str]:
    raw_paths = source_conf.get("selected_paths") or [source_conf.get("root_path", "/")]
    normalized: List[str] = []
    for raw in raw_paths:
        np = _normalize_media_path(str(raw or "/")).rstrip("/") or "/"
        if np not in normalized:
            normalized.append(np)
    return normalized or ["/"]


def _path_in_scope(path: str, scope_path: str) -> bool:
    np = _normalize_media_path(path).rstrip("/") or "/"
    sp = _normalize_media_path(scope_path).rstrip("/") or "/"
    return np == sp or np.startswith(sp + "/")


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
            "User-Agent": f"{APP_NAME}/{APP_VERSION}"
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

def _reload_snapshot_unlocked() -> dict:
    return {
        "is_refreshing": bool(reload_state.get("is_refreshing", False)),
        "queue_size": int(reload_state.get("queue_size", 0)),
        "active_job_id": int(reload_state.get("active_job_id", 0)),
        "job_seq": int(reload_state.get("job_seq", 0)),
        "progress_percent": float(reload_state.get("progress_percent", 0.0)),
        "progress_stage": str(reload_state.get("progress_stage", "idle")),
        "progress_detail": str(reload_state.get("progress_detail", "")),
        "progress_completed_units": int(reload_state.get("progress_completed_units", 0)),
        "progress_total_units": int(reload_state.get("progress_total_units", 0)),
        "sources_total": int(reload_state.get("sources_total", 0)),
        "sources_done": int(reload_state.get("sources_done", 0)),
        "paths_total": int(reload_state.get("paths_total", 0)),
        "paths_done": int(reload_state.get("paths_done", 0)),
        "current_source": str(reload_state.get("current_source", "")),
        "current_path": str(reload_state.get("current_path", "")),
        "last_started_ts": reload_state.get("last_started_ts"),
        "last_finished_ts": reload_state.get("last_finished_ts"),
        "last_duration_ms": float(reload_state.get("last_duration_ms", 0.0)),
        "last_result": str(reload_state.get("last_result", "idle")),
        "last_error": str(reload_state.get("last_error", "")),
        "last_reason": str(reload_state.get("last_reason", "")),
        "total_requested": int(reload_state.get("total_requested", 0)),
        "total_completed": int(reload_state.get("total_completed", 0)),
        "total_failed": int(reload_state.get("total_failed", 0)),
    }


async def _reload_set_progress(
    stage: str,
    detail: str = "",
    *,
    total_units: Optional[int] = None,
    completed_units: Optional[int] = None,
    sources_total: Optional[int] = None,
    sources_done: Optional[int] = None,
    paths_total: Optional[int] = None,
    paths_done: Optional[int] = None,
    current_source: Optional[str] = None,
    current_path: Optional[str] = None,
) -> None:
    async with reload_state_lock:
        if total_units is not None:
            reload_state["progress_total_units"] = max(1, int(total_units))
        if completed_units is not None:
            reload_state["progress_completed_units"] = max(0, int(completed_units))
        if sources_total is not None:
            reload_state["sources_total"] = max(0, int(sources_total))
        if sources_done is not None:
            reload_state["sources_done"] = max(0, int(sources_done))
        if paths_total is not None:
            reload_state["paths_total"] = max(0, int(paths_total))
        if paths_done is not None:
            reload_state["paths_done"] = max(0, int(paths_done))
        if current_source is not None:
            reload_state["current_source"] = str(current_source)
        if current_path is not None:
            reload_state["current_path"] = str(current_path)
        reload_state["progress_stage"] = str(stage or "running")
        reload_state["progress_detail"] = str(detail or "")

        total = max(1, int(reload_state.get("progress_total_units", 1)))
        completed = min(total, max(0, int(reload_state.get("progress_completed_units", 0))))
        reload_state["progress_percent"] = round(min(99.0, (completed / total) * 100.0), 2)


async def _run_reload_once() -> None:
    global alist_instances, video_pool
    async with scan_lock:
        sources = load_config()
        planned_paths = sum(len(_selected_paths_from_conf(src)) for src in sources if _source_random_enabled(src))
        total_units = max(2, 1 + len(sources) + planned_paths + 1)
        completed_units = 0
        sources_done = 0
        paths_done = 0

        await _reload_set_progress(
            stage="preparing",
            detail=f"准备扫描 {len(sources)} 个源",
            total_units=total_units,
            completed_units=completed_units,
            sources_total=len(sources),
            sources_done=sources_done,
            paths_total=planned_paths,
            paths_done=paths_done,
            current_source="",
            current_path="",
        )

        new_instances = {}
        new_video_pool = []
        async with httpx.AsyncClient() as client:
            for src in sources:
                name = src['name']
                url = src['url']
                username = src.get('username') or ""
                password = src.get('password') or ""
                selected_paths = _selected_paths_from_conf(src)
                random_enabled = _source_random_enabled(src)

                token, login_err = await get_source_token(client, url, username, password, verify_cached=True)
                sources_done += 1
                completed_units += 1
                await _reload_set_progress(
                    stage="login",
                    detail=f"{name} 登录{'成功' if token else '失败'}",
                    completed_units=completed_units,
                    sources_done=sources_done,
                    paths_done=paths_done,
                    current_source=name,
                    current_path="",
                )

                if token:
                    normalized_conf = dict(src)
                    normalized_conf["selected_paths"] = selected_paths
                    normalized_conf["random_enabled"] = random_enabled
                    new_instances[name] = {"token": token, "url": url, "conf": normalized_conf}
                    if not random_enabled:
                        await _reload_set_progress(
                            stage="skipped",
                            detail=f"{name} 已禁用随机，跳过扫描",
                            completed_units=completed_units,
                            sources_done=sources_done,
                            paths_done=paths_done,
                            current_source=name,
                            current_path="",
                        )
                        continue
                    source_count = 0
                    print(f"📂 扫描源 '{name}' 的选定路径: {selected_paths}")
                    for root in selected_paths:
                        await _reload_set_progress(
                            stage="scanning",
                            detail=f"{name} 扫描 {root}",
                            completed_units=completed_units,
                            sources_done=sources_done,
                            paths_done=paths_done,
                            current_source=name,
                            current_path=root,
                        )
                        try:
                            videos = await deep_scan_alist(client, url, token, root, name)
                        except Exception as e:
                            print(f"Reload scan failed for source '{name}' path '{root}': {e}")
                            videos = []
                        new_video_pool.extend(videos)
                        source_count += len(videos)
                        paths_done += 1
                        completed_units += 1
                        await _reload_set_progress(
                            stage="scanning",
                            detail=f"{name} 完成 {root} (+{len(videos)})",
                            completed_units=completed_units,
                            sources_done=sources_done,
                            paths_done=paths_done,
                            current_source=name,
                            current_path=root,
                        )
                    print(f"   └─ 源 '{name}' 共扫描到 {source_count} 个媒体文件")
                else:
                    if login_err:
                        print(f"Reload login failed for source '{name}': {login_err}")
                    skipped_paths = len(selected_paths) if random_enabled else 0
                    paths_done += skipped_paths
                    completed_units += skipped_paths
                    await _reload_set_progress(
                        stage="skipped",
                        detail=f"{name} 登录失败，跳过 {skipped_paths} 路径",
                        completed_units=completed_units,
                        sources_done=sources_done,
                        paths_done=paths_done,
                            current_source=name,
                            current_path="",
                        )

        # 同一后端路径仅保留一条，避免多源重叠导致重复随机
        deduped_pool: List[Dict[str, str]] = []
        seen_keys = set()
        for media in new_video_pool:
            src_name = str(media.get("source") or "")
            media_path = _normalize_media_path(str(media.get("path") or "/"))
            clean_base = str(new_instances.get(src_name, {}).get("url", "")).rstrip('/').replace('/dav', '')
            key = f"{clean_base}|{media_path}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if media.get("path") != media_path:
                media = dict(media)
                media["path"] = media_path
            deduped_pool.append(media)
        if len(deduped_pool) != len(new_video_pool):
            print(f"🔁 去重随机池: {len(new_video_pool)} -> {len(deduped_pool)}")
        new_video_pool = deduped_pool

        await _reload_set_progress(
            stage="finalizing",
            detail=f"应用刷新结果，媒体总数 {len(new_video_pool)}",
            completed_units=max(completed_units, total_units - 1),
            sources_done=sources_done,
            paths_done=paths_done,
            current_source="",
            current_path="",
        )

        alist_instances = new_instances
        if new_video_pool:
            random.shuffle(new_video_pool)
            video_pool = new_video_pool
        elif not sources:
            video_pool = []
        else:
            video_pool = []


async def _reload_worker_loop() -> None:
    global reload_worker_task
    while True:
        async with reload_state_lock:
            if int(reload_state.get("queue_size", 0)) <= 0:
                reload_state["is_refreshing"] = False
                reload_state["progress_stage"] = "idle"
                reload_state["progress_detail"] = ""
                reload_worker_task = None
                return
            reload_state["queue_size"] = int(reload_state.get("queue_size", 0)) - 1
            reload_state["is_refreshing"] = True
            reload_state["job_seq"] = int(reload_state.get("job_seq", 0)) + 1
            reload_state["active_job_id"] = int(reload_state["job_seq"])
            reload_state["last_started_ts"] = int(time.time())
            reload_state["last_error"] = ""
            reload_state["last_result"] = "running"
            reload_state["progress_percent"] = 0.0
            reload_state["progress_stage"] = "queued"
            reload_state["progress_detail"] = "等待执行"
            reload_state["progress_completed_units"] = 0
            reload_state["progress_total_units"] = 1
            reload_state["current_source"] = ""
            reload_state["current_path"] = ""
            reload_state["sources_total"] = 0
            reload_state["sources_done"] = 0
            reload_state["paths_total"] = 0
            reload_state["paths_done"] = 0

        started = time.perf_counter()
        err = ""
        try:
            await _run_reload_once()
        except Exception as e:
            err = str(e)
            print(f"Reload job failed: {err}")

        duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        async with reload_state_lock:
            reload_state["last_finished_ts"] = int(time.time())
            reload_state["last_duration_ms"] = duration_ms
            reload_state["is_refreshing"] = False
            reload_state["progress_percent"] = 100.0
            total_units = max(1, int(reload_state.get("progress_total_units", 1)))
            reload_state["progress_completed_units"] = total_units
            if err:
                reload_state["last_error"] = err
                reload_state["last_result"] = "failed"
                reload_state["progress_stage"] = "failed"
                reload_state["progress_detail"] = err[:200]
                reload_state["total_failed"] = int(reload_state.get("total_failed", 0)) + 1
            else:
                reload_state["last_result"] = "success"
                reload_state["progress_stage"] = "completed"
                reload_state["progress_detail"] = "完成"
                reload_state["total_completed"] = int(reload_state.get("total_completed", 0)) + 1


async def request_reload(reason: str = "manual", dedupe: bool = False) -> dict:
    global reload_worker_task
    accepted = True
    async with reload_state_lock:
        if dedupe and (bool(reload_state.get("is_refreshing", False)) or int(reload_state.get("queue_size", 0)) > 0):
            accepted = False
        else:
            reload_state["queue_size"] = int(reload_state.get("queue_size", 0)) + 1
            reload_state["total_requested"] = int(reload_state.get("total_requested", 0)) + 1
            reload_state["last_reason"] = str(reason or "manual")

        if reload_worker_task is None or reload_worker_task.done():
            reload_worker_task = asyncio.create_task(_reload_worker_loop())

        snapshot = _reload_snapshot_unlocked()

    snapshot["accepted"] = accepted
    snapshot["reason"] = str(reason or "manual")
    return snapshot


async def get_reload_state_snapshot() -> dict:
    async with reload_state_lock:
        return _reload_snapshot_unlocked()


async def reload_system_async():
    await request_reload(reason="legacy", dedupe=True)


def _record_stream_result(ok: bool, source: str, reason: str = "") -> None:
    now = time.time()
    stream_events.append({
        "ts": now,
        "ok": bool(ok),
        "source": str(source or ""),
        "reason": str(reason or ""),
    })
    stream_counters["resolve_attempts"] = int(stream_counters.get("resolve_attempts", 0)) + 1
    if ok:
        stream_counters["resolve_success"] = int(stream_counters.get("resolve_success", 0)) + 1
    else:
        stream_counters["resolve_fail"] = int(stream_counters.get("resolve_fail", 0)) + 1
        fail_reasons = stream_counters.get("fail_reasons")
        if not isinstance(fail_reasons, dict):
            fail_reasons = {}
            stream_counters["fail_reasons"] = fail_reasons
        key = str(reason or "unknown")
        fail_reasons[key] = int(fail_reasons.get(key, 0)) + 1


def _stream_health_snapshot(window_sec: int) -> dict:
    now = time.time()
    cutoff = now - max(60, int(window_sec))
    recent = [evt for evt in stream_events if float(evt.get("ts", 0.0)) >= cutoff]
    recent_total = len(recent)
    recent_fail = [evt for evt in recent if not evt.get("ok")]
    reason_counter: Dict[str, int] = {}
    for evt in recent_fail:
        reason = str(evt.get("reason") or "unknown")
        reason_counter[reason] = int(reason_counter.get(reason, 0)) + 1

    fail_rate = 0.0
    if recent_total > 0:
        fail_rate = round((len(recent_fail) / recent_total) * 100.0, 2)

    tail = []
    for evt in recent_fail[-20:]:
        tail.append({
            "ts": int(float(evt.get("ts", 0.0))),
            "source": str(evt.get("source") or ""),
            "reason": str(evt.get("reason") or ""),
        })

    return {
        "window_sec": int(window_sec),
        "window_total": recent_total,
        "window_fail": len(recent_fail),
        "window_fail_rate_pct": fail_rate,
        "window_fail_reasons": reason_counter,
        "window_fail_tail": tail,
        "resolve_attempts": int(stream_counters.get("resolve_attempts", 0)),
        "resolve_success": int(stream_counters.get("resolve_success", 0)),
        "resolve_fail": int(stream_counters.get("resolve_fail", 0)),
        "fail_reasons_total": stream_counters.get("fail_reasons", {}),
        "evicted_stale": int(stream_counters.get("evicted_stale", 0)),
        "last_prune": stream_counters.get("last_prune", {}),
    }


async def _prune_stale_media_once(sample_size: int = 120) -> dict:
    if shared_http_client is None:
        return {"sample_size": int(sample_size), "checked": 0, "removed": 0, "skipped": 0, "note": "http client not ready"}
    if scan_lock.locked():
        return {"sample_size": int(sample_size), "checked": 0, "removed": 0, "skipped": 0, "note": "scan in progress"}
    if not video_pool:
        return {"sample_size": int(sample_size), "checked": 0, "removed": 0, "skipped": 0, "note": "empty pool"}

    sample_size = max(10, min(int(sample_size), 1000))
    snapshot = list(video_pool)
    candidates = random.sample(snapshot, min(sample_size, len(snapshot)))
    checked = 0
    removed = 0
    skipped = 0

    for media in candidates:
        source = str(media.get("source") or "")
        path = str(media.get("path") or "")
        if not source or not path or source not in alist_instances:
            skipped += 1
            continue
        checked += 1
        exists, err = await _probe_media_exists(alist_instances[source], path)
        if err:
            continue
        if exists is False:
            _evict_media_from_pool(source, _normalize_media_path(path))
            removed += 1

    stream_counters["last_prune"] = {
        "ts": int(time.time()),
        "sample_size": sample_size,
        "checked": checked,
        "removed": removed,
        "skipped": skipped,
    }
    return {"sample_size": sample_size, "checked": checked, "removed": removed, "skipped": skipped}


async def periodic_stale_prune_loop() -> None:
    interval = max(120, int(os.getenv("STALE_PRUNE_INTERVAL_SEC", "900")))
    sample_size = max(10, min(int(os.getenv("STALE_PRUNE_SAMPLE_SIZE", "120")), 1000))
    while True:
        await asyncio.sleep(interval)
        try:
            result = await _prune_stale_media_once(sample_size)
            if int(result.get("checked", 0)) > 0 or int(result.get("removed", 0)) > 0:
                print(
                    "Periodic stale prune: "
                    f"sample={result.get('sample_size')} checked={result.get('checked')} "
                    f"removed={result.get('removed')} skipped={result.get('skipped')}"
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Periodic stale prune failed: {e}")

# --- API ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global shared_http_client, stale_prune_task, reload_worker_task
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
    await request_reload(reason="startup", dedupe=True)
    stale_prune_task = asyncio.create_task(periodic_stale_prune_loop())
    yield
    if stale_prune_task is not None:
        stale_prune_task.cancel()
        with suppress(asyncio.CancelledError):
            await stale_prune_task
        stale_prune_task = None
    if reload_worker_task is not None and not reload_worker_task.done():
        reload_worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await reload_worker_task
        reload_worker_task = None
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
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(
                content=f.read(),
                headers={
                    "Cache-Control": "no-store, max-age=0",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
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
    asyncio.create_task(request_reload(reason="source_saved", dedupe=True))
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
        snapshot = await request_reload(reason="manual", dedupe=False)
        return {
            "status": "success",
            "message": "Reload queued",
            "queue_size": snapshot.get("queue_size", 0),
            "active_job_id": snapshot.get("active_job_id", 0),
            "progress_percent": snapshot.get("progress_percent", 0.0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/reload/status")
async def get_reload_status():
    """获取当前刷新状态"""
    snap = await get_reload_state_snapshot()
    return {
        "is_refreshing": bool(snap.get("is_refreshing", False)),
        "sources_count": len(alist_instances),
        "video_pool_size": len(video_pool),
        "queue_size": int(snap.get("queue_size", 0)),
        "active_job_id": int(snap.get("active_job_id", 0)),
        "progress_percent": float(snap.get("progress_percent", 0.0)),
        "progress_stage": str(snap.get("progress_stage", "idle")),
        "progress_detail": str(snap.get("progress_detail", "")),
        "progress_completed_units": int(snap.get("progress_completed_units", 0)),
        "progress_total_units": int(snap.get("progress_total_units", 0)),
        "sources_total": int(snap.get("sources_total", 0)),
        "sources_done": int(snap.get("sources_done", 0)),
        "paths_total": int(snap.get("paths_total", 0)),
        "paths_done": int(snap.get("paths_done", 0)),
        "current_source": str(snap.get("current_source", "")),
        "current_path": str(snap.get("current_path", "")),
        "last_started_ts": snap.get("last_started_ts"),
        "last_finished_ts": snap.get("last_finished_ts"),
        "last_duration_ms": float(snap.get("last_duration_ms", 0.0)),
        "last_result": str(snap.get("last_result", "idle")),
        "last_error": str(snap.get("last_error", "")),
        "last_reason": str(snap.get("last_reason", "")),
        "total_requested": int(snap.get("total_requested", 0)),
        "total_completed": int(snap.get("total_completed", 0)),
        "total_failed": int(snap.get("total_failed", 0)),
    }


@app.get("/v1/reload/queue")
async def get_reload_queue():
    return await get_reload_status()


@app.get("/v1/stream/health")
async def get_stream_health(window_sec: int = 600):
    window_sec = max(60, min(int(window_sec), 86400))
    payload = _stream_health_snapshot(window_sec)
    snap = await get_reload_state_snapshot()
    payload.update({
        "is_refreshing": bool(snap.get("is_refreshing", False)),
        "reload_queue_size": int(snap.get("queue_size", 0)),
        "reload_progress_percent": float(snap.get("progress_percent", 0.0)),
        "reload_progress_stage": str(snap.get("progress_stage", "idle")),
        "sources_count": len(alist_instances),
        "video_pool_size": len(video_pool),
        "stream_events_cached": len(stream_events),
    })
    return payload


@app.post("/v1/stream/prune_stale")
async def prune_stale_stream_entries(sample_size: int = 120):
    result = await _prune_stale_media_once(sample_size)
    return {"status": "success", **result, "video_pool_size": len(video_pool)}


@app.delete("/v1/sources/{name}")
async def remove_source(name: str):
    current = load_config()
    current = [s for s in current if s['name'] != name]
    save_config(current)
    asyncio.create_task(request_reload(reason="source_deleted", dedupe=True))
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
        asyncio.create_task(request_reload(reason="empty_pool", dedupe=True))
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


def _evict_media_from_pool(source: str, path: str) -> None:
    global video_pool
    before = len(video_pool)
    video_pool = [v for v in video_pool if not (v.get('source') == source and v.get('path') == path)]
    after = len(video_pool)
    if after != before:
        stream_counters["evicted_stale"] = int(stream_counters.get("evicted_stale", 0)) + (before - after)
        print(f"Evicted stale media from pool: source={source}, path={path}")


def _source_clean_base_url(source: str) -> str:
    instance = alist_instances.get(source) or {}
    return str(instance.get("url") or "").rstrip('/').replace('/dav', '')


def _evict_media_by_backend_path(clean_base_url: str, path: str) -> int:
    global video_pool
    target_path = _normalize_media_path(path)
    removed = 0
    kept = []
    for media in video_pool:
        media_source = str(media.get("source") or "")
        media_path = _normalize_media_path(str(media.get("path") or "/"))
        media_base = _source_clean_base_url(media_source)
        same_backend = (not clean_base_url) or (media_base == clean_base_url)
        if same_backend and media_path == target_path:
            removed += 1
            continue
        kept.append(media)
    if removed:
        video_pool = kept
        stream_counters["evicted_stale"] = int(stream_counters.get("evicted_stale", 0)) + removed
        print(f"Evicted media by backend+path: base={clean_base_url}, path={target_path}, removed={removed}")
    return removed


def _is_path_in_any_random_scope(path: str) -> bool:
    target_path = _normalize_media_path(path)
    for instance in alist_instances.values():
        conf = instance.get("conf", {})
        if not _source_random_enabled(conf):
            continue
        for selected in _selected_paths_from_conf(conf):
            if _path_in_scope(target_path, selected):
                return True
    return False


async def _resolve_media_raw_url(source: str, path: str, evict_on_not_found: bool = True) -> str:
    probe_path = _normalize_media_path(path)
    if source not in alist_instances:
        _record_stream_result(False, source, "source_not_found")
        raise HTTPException(status_code=404, detail="Source not found")

    if shared_http_client is None:
        _record_stream_result(False, source, "http_client_not_ready")
        raise HTTPException(status_code=503, detail="HTTP client not initialized")

    instance = alist_instances[source]
    clean_url = instance['url'].rstrip('/').replace('/dav', '')
    conf = instance.get('conf', {})
    username = str(conf.get('username') or "")
    password = str(conf.get('password') or "")

    last_err = ""
    # 并发下 OpenList 偶发瞬时失败，做短重试；对象确实不存在则立刻淘汰池中脏条目
    for attempt in range(3):
        token = instance.get('token') or ""
        details, err = await AlistHelper.get_file_details_with_error(shared_http_client, clean_url, token, probe_path)
        if err and "token is invalidated" in err.lower():
            token, login_err = await get_source_token(shared_http_client, clean_url, username, password, force_refresh=True)
            if not token:
                _record_stream_result(False, source, "login_failed")
                raise HTTPException(status_code=400, detail=login_err or "Login failed")
            instance['token'] = token
            details, err = await AlistHelper.get_file_details_with_error(shared_http_client, clean_url, token, probe_path)

        if err:
            last_err = err
            if _is_object_not_found_error(err):
                # 并发高峰下个别后端会瞬时报 not found，先短重试再判定
                if attempt < 2:
                    await asyncio.sleep(0.08 * (2 ** attempt))
                    continue
                if evict_on_not_found:
                    _evict_media_from_pool(source, probe_path)
                _record_stream_result(False, source, "object_not_found")
                raise HTTPException(status_code=404, detail="object not found")
            if attempt < 2:
                await asyncio.sleep(0.08 * (2 ** attempt))
                continue
            _record_stream_result(False, source, "alist_error")
            raise HTTPException(status_code=502, detail=err)

        if details and details.get('raw_url'):
            _record_stream_result(True, source)
            return str(details.get('raw_url'))

        last_err = "File unavailable"
        if attempt < 2:
            await asyncio.sleep(0.08 * (2 ** attempt))
            continue
        _record_stream_result(False, source, "file_unavailable")
        raise HTTPException(status_code=404, detail="File unavailable")

    _record_stream_result(False, source, "resolve_failed")
    raise HTTPException(status_code=502, detail=last_err or "stream resolve failed")


def _normalize_media_path(path: str) -> str:
    if not isinstance(path, str):
        return "/"
    clean = "/" + path.strip().lstrip("/")
    clean = re.sub(r"/+", "/", clean)
    return clean or "/"


def _join_media_path(dir_path: str, file_name: str) -> str:
    base = _normalize_media_path(dir_path)
    if base == "/":
        return _normalize_media_path(file_name)
    return _normalize_media_path(f"{base.rstrip('/')}/{str(file_name).lstrip('/')}")


def _is_object_not_found_error(message: Optional[str]) -> bool:
    if not message:
        return False
    msg = message.lower()
    if "object not found" in msg:
        return True
    if "file not found" in msg:
        return True
    return "not found" in msg and "token" not in msg


async def _probe_media_exists(instance: dict, path: str) -> tuple[Optional[bool], Optional[str]]:
    if shared_http_client is None:
        return None, "HTTP client not initialized"

    clean_url = instance['url'].rstrip('/').replace('/dav', '')
    conf = instance.get('conf', {})
    username = str(conf.get('username') or "")
    password = str(conf.get('password') or "")
    token = str(instance.get('token') or "")
    query_path = _normalize_media_path(path)

    details, err = await AlistHelper.get_file_details_with_error(shared_http_client, clean_url, token, query_path)
    if err and "token is invalidated" in err.lower():
        new_token, login_err = await get_source_token(
            shared_http_client, clean_url, username, password, force_refresh=True
        )
        if not new_token:
            return None, login_err or "Login failed"
        token = new_token
        instance['token'] = token
        details, err = await AlistHelper.get_file_details_with_error(shared_http_client, clean_url, token, query_path)

    if err:
        if _is_object_not_found_error(err):
            return False, None
        return None, err
    return bool(details), None


async def _verify_delete_committed(instance: dict, file_path: str) -> tuple[bool, str]:
    target = _normalize_media_path(file_path)
    # OpenList/后端存储状态可能有短暂延迟，做短轮询避免“假成功”
    delays = (0.0, 0.5, 1.0, 2.0, 3.0)
    last_err = ""
    for delay in delays:
        if delay > 0:
            await asyncio.sleep(delay)
        exists, err = await _probe_media_exists(instance, target)
        if err:
            last_err = err
            continue
        if exists is False:
            return True, ""
    if last_err:
        return False, f"删除后复核失败: {last_err}"
    return False, f"删除后复核失败: 文件仍存在 {target}"


async def _verify_move_committed(instance: dict, src_path: str, dst_path: str) -> tuple[bool, str]:
    src = _normalize_media_path(src_path)
    dst = _normalize_media_path(dst_path)
    delays = (0.0, 0.5, 1.0, 2.0, 3.0)
    last_err = ""
    last_src_exists: Optional[bool] = None
    last_dst_exists: Optional[bool] = None

    for delay in delays:
        if delay > 0:
            await asyncio.sleep(delay)
        src_exists, src_err = await _probe_media_exists(instance, src)
        dst_exists, dst_err = await _probe_media_exists(instance, dst)
        if src_err or dst_err:
            last_err = "; ".join([x for x in [src_err, dst_err] if x])
            continue
        last_src_exists = src_exists
        last_dst_exists = dst_exists
        if src_exists is False and dst_exists is True:
            return True, ""

    if last_err:
        return False, f"移动后复核失败: {last_err}"
    return False, (
        f"移动后复核超时(源是否存在={last_src_exists}, 目标是否存在={last_dst_exists})，"
        "可能仍在后台任务执行中，请稍后刷新确认"
    )


@app.api_route("/v1/stream", methods=["GET", "HEAD"])
async def stream_video(request: Request, source: str, path: str):
    raw_url = await _resolve_media_raw_url(source, path, evict_on_not_found=(request.method != "HEAD"))
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

    pre_exists, pre_err = await _probe_media_exists(instance, file_path)
    if pre_err:
        raise HTTPException(status_code=502, detail=pre_err)
    if pre_exists is False:
        raise HTTPException(status_code=404, detail=f"源文件不存在: {file_path}")

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
        verified, verify_msg = await _verify_delete_committed(instance, file_path)
        if not verified:
            raise HTTPException(status_code=500, detail=verify_msg)
        evicted = _evict_media_by_backend_path(instance['url'].rstrip('/').replace('/dav', ''), file_path)
        return {"status": "success", "evicted": evicted}
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

    src_exists, src_err = await _probe_media_exists(instance, src_path)
    if src_err:
        raise HTTPException(status_code=502, detail=src_err)
    if src_exists is False:
        raise HTTPException(status_code=404, detail=f"源文件不存在: {src_path}")

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
            dst_path = _join_media_path(dst_dir, file_name)
            verified, verify_msg = await _verify_move_committed(instance, src_path, dst_path)
            if not verified:
                raise HTTPException(status_code=500, detail=verify_msg)
            evicted_old = _evict_media_by_backend_path(base_url, src_path)
            in_random_scope = _is_path_in_any_random_scope(dst_path)
            evicted_dst = 0
            if not in_random_scope:
                evicted_dst = _evict_media_by_backend_path(base_url, dst_path)
            return {
                "status": "success",
                "dst_path": dst_path,
                "in_random_scope": in_random_scope,
                "evicted_old": evicted_old,
                "evicted_dst": evicted_dst,
            }
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
    norm_selected = _selected_paths_from_conf(conf)

    def is_path_allowed(item_path: str, is_dir: bool) -> bool:
        """检查路径是否在 selected_paths 范围内（或是其祖先目录）"""
        np = item_path.rstrip('/') or '/'
        for sp in norm_selected:
            # 文件/目录在选定路径内部
            if _path_in_scope(np, sp):
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
