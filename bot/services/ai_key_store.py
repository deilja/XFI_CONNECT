"""Encrypted-at-rest AI provider key storage.

The encryption master secret is supplied by the deployment environment; it is
never accepted from the AI model and never committed to the repository.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path


class AIKeyStore:
    def __init__(self, path: str | Path, master_key: str | None = None):
        self.path = Path(path)
        self.master_key = (master_key or os.getenv("XFI_AI_KEYSTORE_MASTER_KEY", "")).encode()
        if len(self.master_key) < 32:
            raise ValueError("XFI_AI_KEYSTORE_MASTER_KEY must contain at least 32 bytes")

    def _keystream(self, nonce: bytes, length: int) -> bytes:
        out = bytearray()
        counter = 0
        while len(out) < length:
            out.extend(hmac.new(self.master_key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
            counter += 1
        return bytes(out[:length])

    def _crypt(self, data: bytes, nonce: bytes) -> bytes:
        stream = self._keystream(nonce, len(data))
        return bytes(a ^ b for a, b in zip(data, stream))

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        envelope = json.loads(self.path.read_text(encoding="utf-8"))
        nonce = base64.b64decode(envelope["nonce"])
        ciphertext = base64.b64decode(envelope["ciphertext"])
        return json.loads(self._crypt(ciphertext, nonce).decode("utf-8"))

    def _save(self, values: dict[str, str]) -> None:
        nonce = os.urandom(16)
        plaintext = json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ciphertext = self._crypt(plaintext, nonce)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps({"version": 1, "nonce": base64.b64encode(nonce).decode(), "ciphertext": base64.b64encode(ciphertext).decode()}), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        os.chmod(self.path, 0o600)

    def set(self, provider: str, api_key: str) -> None:
        if not api_key.strip() or len(api_key) > 4096:
            raise ValueError("Invalid API key")
        values = self._load()
        values[provider] = api_key.strip()
        self._save(values)

    def get(self, provider: str) -> str | None:
        return self._load().get(provider)

    def delete(self, provider: str) -> None:
        values = self._load()
        values.pop(provider, None)
        self._save(values)

    def configured(self, provider: str) -> bool:
        return bool(self.get(provider))
