from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

from app.core.config import get_settings

import structlog
log = structlog.get_logger()


def _storage_root() -> Path:
    s = get_settings()
    root = Path(s.STORAGE_PATH)
    root.mkdir(parents=True, exist_ok=True)
    return root


def upload_bytes(bucket: str, path: str, data: bytes, content_type: str) -> Tuple[bool, str]:
    """Store bytes locally under storage/<bucket>/<path>."""
    try:
        # Try Supabase first if configured
        s = get_settings()
        if s.SUPABASE_URL and s.SUPABASE_SERVICE_KEY and not s.SUPABASE_URL.startswith("your_"):
            from supabase import create_client
            sb = create_client(s.SUPABASE_URL, s.SUPABASE_SERVICE_KEY)
            res = sb.storage.from_(bucket).upload(path, data, {"content-type": content_type, "upsert": False})
            if isinstance(res, dict) and res.get("error"):
                raise RuntimeError(str(res["error"]))
            return True, path
    except Exception as e:
        log.warning("storage.supabase_failed_fallback_local", error=str(e))

    # Local filesystem fallback
    dest = _storage_root() / bucket / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    log.info("storage.local_upload", path=str(dest))
    return True, path


def download_bytes(bucket: str, path: str) -> Tuple[bytes | None, str | None]:
    """Download bytes — tries Supabase first, falls back to local."""
    try:
        s = get_settings()
        if s.SUPABASE_URL and s.SUPABASE_SERVICE_KEY and not s.SUPABASE_URL.startswith("your_"):
            from supabase import create_client
            sb = create_client(s.SUPABASE_URL, s.SUPABASE_SERVICE_KEY)
            data = sb.storage.from_(bucket).download(path)
            return data, None
    except Exception as e:
        log.warning("storage.supabase_download_failed_fallback_local", error=str(e))

    local = _storage_root() / bucket / path
    if local.exists():
        return local.read_bytes(), None
    return None, f"File not found: {path}"


def get_signed_url(bucket: str, path: str, expires_in: int = 3600) -> str:
    try:
        s = get_settings()
        if s.SUPABASE_URL and s.SUPABASE_SERVICE_KEY and not s.SUPABASE_URL.startswith("your_"):
            from supabase import create_client
            sb = create_client(s.SUPABASE_URL, s.SUPABASE_SERVICE_KEY)
            res = sb.storage.from_(bucket).create_signed_url(path, expires_in)
            return res.get("signedURL", "")
    except Exception:
        pass
    return f"/storage/{bucket}/{path}"


def upload_file(bucket: str, path: str, file_path: str, content_type: str = "application/octet-stream") -> Tuple[bool, str | None]:
    try:
        data = Path(file_path).read_bytes()
        success, result = upload_bytes(bucket, path, data, content_type)
        return (True, None) if success else (False, result)
    except Exception as e:
        return False, str(e)
