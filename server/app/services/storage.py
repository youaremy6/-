"""Local media store with short-lived HMAC signed URLs (spec 6.2).

The P0 deployment keeps generated audio on the BFF's local disk; the same
interface can be backed by an object-storage bucket later.  Signed URLs never
outlive 24 hours and the signing secret is never exposed.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from pathlib import Path

_KEY_RE = re.compile(r"^[a-f0-9]{32}\.(wav|mp3)$")
_CONTENT_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg"}


class MediaStore:
    def __init__(
        self,
        media_dir: Path,
        signing_secret: str,
        public_base_url: str,
        default_ttl_seconds: int = 3600,
    ) -> None:
        self.media_dir = Path(media_dir)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self._secret = signing_secret.encode("utf-8")
        self.public_base_url = public_base_url.rstrip("/")
        self.default_ttl_seconds = min(86_400, default_ttl_seconds)

    def put(self, data: bytes, ext: str = ".wav") -> str:
        ext = ext if ext in _CONTENT_TYPES else ".wav"
        key = hashlib.sha256(data).hexdigest()[:32] + ext
        path = self.media_dir / key
        if not path.exists():
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return key

    def exists(self, key: str) -> bool:
        return bool(_KEY_RE.match(key)) and (self.media_dir / key).exists()

    def path(self, key: str) -> Path:
        if not _KEY_RE.match(key):
            raise ValueError("invalid media key")
        return self.media_dir / key

    def content_type(self, key: str) -> str:
        return _CONTENT_TYPES.get(Path(key).suffix, "application/octet-stream")

    def sign(self, key: str, ttl_seconds: int | None = None) -> str:
        ttl = min(86_400, ttl_seconds or self.default_ttl_seconds)
        expires = int(time.time()) + ttl
        signature = hmac.new(
            self._secret, f"{key}:{expires}".encode("utf-8"), hashlib.sha256
        ).hexdigest()[:32]
        return f"{self.public_base_url}/media/{key}?exp={expires}&sig={signature}"

    def verify(self, key: str, expires: int, signature: str) -> bool:
        if not _KEY_RE.match(key) or expires < int(time.time()):
            return False
        expected = hmac.new(
            self._secret, f"{key}:{expires}".encode("utf-8"), hashlib.sha256
        ).hexdigest()[:32]
        return hmac.compare_digest(expected, signature)

    def delete(self, key: str) -> None:
        try:
            self.path(key).unlink(missing_ok=True)
        except ValueError:
            return
