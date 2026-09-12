"""Image helpers: decode browser payloads, persist outputs."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from pathlib import Path

from ..config import settings

DATA_URL_RE = re.compile(r"^data:(?P<mime>image/[a-zA-Z0-9.+-]+);base64,(?P<data>.+)$", re.S)
MAGIC = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"RIFF": "image/webp",
}


class ImageDecodeError(ValueError):
    pass


def decode_image(payload: str) -> tuple[bytes, str]:
    """Accept a data URL or bare base64 string. Returns ``(bytes, mime)``."""
    raw = payload.strip()
    mime: str | None = None
    match = DATA_URL_RE.match(raw)
    if match:
        mime = match.group("mime")
        raw = match.group("data")
    raw = re.sub(r"\s+", "", raw)
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageDecodeError(f"invalid base64 image payload: {exc}") from exc

    limit = settings.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise ImageDecodeError(f"image exceeds {settings.max_upload_mb} MB limit")

    detected = next((m for magic, m in MAGIC.items() if data.startswith(magic)), None)
    if detected is None:
        raise ImageDecodeError("payload is not a PNG, JPEG or WebP image")
    return data, mime or detected


def sha256_hex(*parts: bytes | str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part if isinstance(part, bytes) else part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def save_output(data: bytes, name: str, subdir: str = "results") -> str:
    """Write bytes under ``settings.output_dir``; return the relative path."""
    folder = settings.output_dir / subdir
    folder.mkdir(parents=True, exist_ok=True)
    rel = f"{subdir}/{name}"
    (settings.output_dir / rel).write_bytes(data)
    return rel


def output_abs(rel_path: str) -> Path:
    return settings.output_dir / rel_path


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
