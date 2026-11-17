"""checkpoint正文专用AES256-GCM；完整scope和物理位置AAD，禁止自动造key。"""

import json
import os
from dataclasses import asdict

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from efficiency_platform_agent.core.memory_thread import (
    CheckpointCiphertext,
    CheckpointLocation,
)


class AesGcmCheckpointBodyCipher:
    def __init__(self, key: bytes, key_version: str):
        if (
            not isinstance(key, bytes)
            or len(key) != 32
            or not isinstance(key_version, str)
            or not key_version
            or len(key_version) > 128
            or not key_version.isascii()
        ):
            raise ValueError("CHECKPOINT_ENCRYPTION_KEY_REQUIRED")
        self._aes, self.key_version = AESGCM(key), key_version

    def _aad(self, location: CheckpointLocation) -> bytes:
        return json.dumps(
            ["memory-checkpoint/1", self.key_version, asdict(location)],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()

    def seal(self, location: CheckpointLocation, body: bytes) -> CheckpointCiphertext:
        nonce = os.urandom(12)
        return CheckpointCiphertext(
            self._aes.encrypt(nonce, body, self._aad(location)), nonce, self.key_version
        )

    def open(self, location: CheckpointLocation, body: CheckpointCiphertext) -> bytes:
        try:
            if body.key_version != self.key_version:
                raise ValueError("CHECKPOINT_BODY_UNAVAILABLE")
            return self._aes.decrypt(body.nonce, body.ciphertext, self._aad(location))
        except (InvalidTag, ValueError, TypeError):
            raise ValueError("CHECKPOINT_BODY_UNAVAILABLE") from None
