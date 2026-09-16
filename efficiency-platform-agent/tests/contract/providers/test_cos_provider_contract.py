"""COS Artifact Provider 的离线 SDK Stub 测试。"""

from __future__ import annotations

import io
import unittest

from efficiency_platform_agent.providers.storage.cos import (
    ArtifactDeleteRequest,
    ArtifactGetRequest,
    ArtifactPutRequest,
    ArtifactSignRequest,
    CosArtifactProvider,
)


class _CosStub:
    def __init__(self):
        self.objects = {}
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(("put", kwargs["Key"]))
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def head_object(self, **kwargs):
        self.calls.append(("head", kwargs["Key"]))

    def get_object(self, **kwargs):
        self.calls.append(("get", kwargs["Key"]))
        return {"Body": io.BytesIO(self.objects[kwargs["Key"]])}

    def get_presigned_url(self, **kwargs):
        self.calls.append(("sign", kwargs["Key"]))
        return "https://signed.invalid/s7"

    def delete_object(self, **kwargs):
        self.calls.append(("delete", kwargs["Key"]))
        self.objects.pop(kwargs["Key"], None)


class CosProviderContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifecycle_isolated_and_hashed(self):
        stub = _CosStub()
        provider = CosArtifactProvider(stub, bucket="bucket", region="ap-shanghai")
        record = await provider.put(
            ArtifactPutRequest("run1", "tenant1", "doc1", b"abc")
        )
        self.assertTrue(record.key.startswith("s7/run1/"))
        self.assertEqual(
            await provider.get(ArtifactGetRequest("run1", "tenant1", "doc1")), b"abc"
        )
        self.assertTrue(
            (
                await provider.sign_download(
                    ArtifactSignRequest("run1", "tenant1", "doc1")
                )
            ).url.startswith("https://")
        )
        await provider.delete(ArtifactDeleteRequest("run1", "tenant1", "doc1"))
        self.assertNotIn(record.key, stub.objects)

    async def test_existing_object_is_not_overwritten(self):
        provider = CosArtifactProvider(_CosStub(), bucket="bucket", region="region")
        request = ArtifactPutRequest("run", "tenant", "doc", b"x")
        await provider.put(request)
        with self.assertRaises(ValueError):
            await provider.put(request)

    async def test_limits_and_unsafe_keys_rejected(self):
        provider = CosArtifactProvider(_CosStub(), bucket="bucket", region="region")
        with self.assertRaises(ValueError):
            await provider.put(ArtifactPutRequest("run/evil", "tenant", "a", b"x"))
        with self.assertRaises(ValueError):
            await provider.put(
                ArtifactPutRequest("run", "tenant", "a", b"x" * (1024 * 1024 + 1))
            )
        for n in range(3):
            await provider.put(ArtifactPutRequest("run", "tenant", f"a{n}", b"x"))
        with self.assertRaises(ValueError):
            await provider.put(ArtifactPutRequest("run", "tenant", "a3", b"x"))

    async def test_corrupted_object_fails_integrity_check(self):
        stub = _CosStub()
        provider = CosArtifactProvider(stub, bucket="bucket", region="region")
        request = ArtifactPutRequest("run", "tenant", "doc", b"abc")
        await provider.put(request)
        stub.objects[next(iter(stub.objects))] = b"tampered"
        with self.assertRaisesRegex(ValueError, "ARTIFACT_INTEGRITY_FAILED"):
            await provider.get(ArtifactGetRequest("run", "tenant", "doc"))

    async def test_missing_sdk_method_fails_closed(self):
        class IncompleteStub:
            def put_object(self, **kwargs):
                del kwargs

        provider = CosArtifactProvider(
            IncompleteStub(), bucket="bucket", region="region"
        )
        await provider.put(ArtifactPutRequest("run", "tenant", "doc", b"abc"))
        with self.assertRaisesRegex(TypeError, "COS_METHOD_NOT_AVAILABLE"):
            await provider.head(ArtifactGetRequest("run", "tenant", "doc"))


__all__ = ["CosProviderContractTests"]
