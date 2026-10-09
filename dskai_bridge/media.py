"""Authenticated media download and immutable cache.

Whole-asset hash verification precedes playback. Starlette FileResponse handles local
Range/HEAD requests, even when the Muse endpoint does not support seeking.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from .models import Media
from .transport import TransportError


class MediaCache:
    def __init__(self, root, connection_file, allowed_origins, client=None, max_bytes=1_000_000_000):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.connection_file = Path(connection_file)
        self.allowed_origins = set(allowed_origins)
        self.client = client or httpx.Client(timeout=httpx.Timeout(120, connect=10), follow_redirects=False)
        self.max_bytes = max_bytes

    def connection(self):
        # Runtime file is private and atomically replaced by the operator on tunnel rotation.
        # Never take a URL or Bearer token from a GitHub result or a browser argument.
        try:
            cfg = json.loads(self.connection_file.read_text())
            origin = cfg["origin"]
            url = urlsplit(origin)
            if (url.scheme != "https" or url.username or url.password or url.path
                    or url.query or url.fragment or origin not in self.allowed_origins):
                raise ValueError()
            token = cfg["token"]
            if not isinstance(token, str) or len(token) < 16 or any(c in token for c in "\r\n"):
                raise ValueError()
            return origin, token
        except (OSError, ValueError, KeyError):
            raise TransportError("MEDIA_CONNECTION_CONFIGURATION_REQUIRED") from None

    def fetch(self, media):
        m = Media.model_validate(media)
        target = self.root / m.sha256
        if target.is_file():
            if target.stat().st_size == m.size_bytes and self.hash_file(target) == m.sha256:
                return target
            raise TransportError("CACHED_MEDIA_INTEGRITY_FAILURE")
        if m.size_bytes > self.max_bytes:
            raise TransportError("MEDIA_SIZE_LIMIT")
        origin, token = self.connection()
        url = origin + "/files/" + quote(m.relpath, safe="/")
        temp_path = None
        try:
            with self.client.stream("GET", url, headers={"Authorization": "Bearer " + token,
                                                        "Accept-Encoding": "identity"}) as response:
                if response.status_code in (401, 403):
                    raise TransportError("MEDIA_AUTH_REQUIRED")
                if response.status_code != 200:
                    # No redirect following or /media fallback: do not leak Bearer credentials.
                    raise TransportError("MEDIA_HTTP_" + str(response.status_code))
                size, hashed = 0, hashlib.sha256()
                with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as output:
                    temp_path = Path(output.name)
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > min(m.size_bytes, self.max_bytes):
                            raise TransportError("MEDIA_SIZE_MISMATCH")
                        hashed.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if size != m.size_bytes or hashed.hexdigest() != m.sha256:
                    raise TransportError("MEDIA_INTEGRITY_FAILURE")
                os.replace(temp_path, target)
                temp_path = None
                return target
        except httpx.TransportError:
            raise TransportError("MEDIA_NETWORK_UNAVAILABLE") from None
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    @staticmethod
    def hash_file(path):
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
