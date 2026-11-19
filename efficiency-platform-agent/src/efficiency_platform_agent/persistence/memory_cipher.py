"""独立密钥加密临时授权快照，AAD禁止跨租户或执行搬移。"""

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True, slots=True)
class SealedMemorySnapshot:
    ciphertext: bytes = field(repr=False)
    nonce: bytes = field(repr=False)
    key_version: str


class MemorySnapshotCipher:
    def __init__(self, current: str, keys: Mapping[str, bytes]):
        if (
            not current
            or current not in keys
            or len(current) > 128
            or not current.isascii()
            or any(
                not isinstance(key, bytes) or len(key) != 32 for key in keys.values()
            )
        ):
            raise ValueError("MEMORY_ENCRYPTION_KEY_REQUIRED")
        self._current = current
        self._keys = dict(keys)

    @staticmethod
    def _aad(tenant: str, execution: str, runtime: str, version: str) -> bytes:
        return json.dumps(
            ["memory-execution/1", tenant, execution, runtime, version],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    def seal(
        self,
        tenant: str,
        execution: str,
        runtime: str,
        value: bytes,
        *,
        key_version: str | None = None,
    ) -> SealedMemorySnapshot:
        version = self._current if key_version is None else key_version
        if version not in self._keys:
            raise ValueError("MEMORY_SNAPSHOT_UNAVAILABLE")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._keys[version]).encrypt(
            nonce, value, self._aad(tenant, execution, runtime, version)
        )
        return SealedMemorySnapshot(ciphertext, nonce, version)

    def open(
        self, tenant: str, execution: str, runtime: str, snapshot: SealedMemorySnapshot
    ) -> bytes:
        try:
            return AESGCM(self._keys[snapshot.key_version]).decrypt(
                snapshot.nonce,
                snapshot.ciphertext,
                self._aad(tenant, execution, runtime, snapshot.key_version),
            )
        except (KeyError, InvalidTag, ValueError):
            raise ValueError("MEMORY_SNAPSHOT_UNAVAILABLE") from None

    def seal_journal(
        self,
        scope: tuple[str | None, ...],
        execution: str,
        runtime: str,
        record_id: str,
        kind: str,
        value: bytes,
        *,
        binding: str | None = None,
        key_version: str | None = None,
    ) -> SealedMemorySnapshot:
        version = self._current if key_version is None else key_version
        if version not in self._keys:
            raise ValueError("MEMORY_SNAPSHOT_UNAVAILABLE")
        aad = json.dumps(
            [
                "memory-refresh-body/1",
                list(scope),
                execution,
                runtime,
                record_id,
                kind,
                version,
            ]
            + ([] if binding is None else [binding]),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        nonce = os.urandom(12)
        return SealedMemorySnapshot(
            AESGCM(self._keys[version]).encrypt(nonce, value, aad),
            nonce,
            version,
        )

    def open_journal(
        self,
        scope: tuple[str | None, ...],
        execution: str,
        runtime: str,
        record_id: str,
        kind: str,
        snapshot: SealedMemorySnapshot,
        *,
        binding: str | None = None,
    ) -> bytes:
        aad = json.dumps(
            [
                "memory-refresh-body/1",
                list(scope),
                execution,
                runtime,
                record_id,
                kind,
                snapshot.key_version,
            ]
            + ([] if binding is None else [binding]),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        try:
            return AESGCM(self._keys[snapshot.key_version]).decrypt(
                snapshot.nonce, snapshot.ciphertext, aad
            )
        except (KeyError, InvalidTag, ValueError):
            raise ValueError("MEMORY_SNAPSHOT_UNAVAILABLE") from None
