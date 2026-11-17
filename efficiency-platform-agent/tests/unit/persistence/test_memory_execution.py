"""技术授权只用独立AES密钥，完整身份AAD绑定，不能降级明文。"""

import pytest

from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher


def test_snapshot_cipher_never_contains_plaintext_and_binds_full_identity():
    cipher = MemorySnapshotCipher("v1", {"v1": bytes(range(32))})
    sealed = cipher.seal(
        "tenant", "execution", "runtime", b'{"value":"synthetic-private-value"}'
    )
    assert b"synthetic-private-value" not in sealed.ciphertext
    assert (
        cipher.open("tenant", "execution", "runtime", sealed)
        == b'{"value":"synthetic-private-value"}'
    )
    for binding in [
        ("other", "execution", "runtime"),
        ("tenant", "other", "runtime"),
        ("tenant", "execution", "other"),
    ]:
        with pytest.raises(ValueError, match="MEMORY_SNAPSHOT_UNAVAILABLE"):
            cipher.open(*binding, sealed)
    other = MemorySnapshotCipher("v2", {"v2": bytes(reversed(range(32)))})
    with pytest.raises(ValueError, match="MEMORY_SNAPSHOT_UNAVAILABLE"):
        other.open("tenant", "execution", "runtime", sealed)


@pytest.mark.parametrize("keys", [{}, {"v1": b"short"}])
def test_missing_key_has_no_plaintext_fallback(keys):
    with pytest.raises(ValueError, match="MEMORY_ENCRYPTION_KEY_REQUIRED"):
        MemorySnapshotCipher("v1", keys)
