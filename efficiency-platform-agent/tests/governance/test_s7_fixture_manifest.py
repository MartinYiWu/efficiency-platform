"""S7 固定样本生成治理测试。"""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_s7_fixtures import build


class S7FixtureManifestTests(unittest.TestCase):
    def test_same_seed_produces_same_manifest_and_hashes(self):
        with (
            tempfile.TemporaryDirectory() as first,
            tempfile.TemporaryDirectory() as second,
        ):
            build(Path(first), "governance")
            build(Path(second), "governance")
            self.assertEqual(
                (Path(first) / "manifest.json").read_bytes(),
                (Path(second) / "manifest.json").read_bytes(),
            )
            names = [
                item["name"]
                for item in json.loads((Path(first) / "manifest.json").read_text())[
                    "fixtures"
                ]
            ]
            self.assertEqual(len(names), 12)
            for name in names:
                first_hash = hashlib.sha256(
                    (Path(first) / name).read_bytes()
                ).hexdigest()
                second_hash = hashlib.sha256(
                    (Path(second) / name).read_bytes()
                ).hexdigest()
                self.assertEqual(first_hash, second_hash)
                entry = next(
                    item
                    for item in json.loads((Path(first) / "manifest.json").read_text())[
                        "fixtures"
                    ]
                    if item["name"] == name
                )
                self.assertEqual(first_hash, entry["sha256"])
                self.assertIn("expected_structure", entry)
                payload = (Path(first) / name).read_bytes()
                if name.endswith((".docx", ".xlsx")):
                    self.assertTrue(payload.startswith(b"PK"))
                elif name.endswith(".pdf"):
                    self.assertTrue(payload.startswith(b"%PDF-"))
                elif name.endswith(".png"):
                    if name.startswith("rejected_"):
                        self.assertFalse(payload.startswith(b"\x89PNG\r\n\x1a\n"))
                    else:
                        self.assertTrue(payload.startswith(b"\x89PNG\r\n\x1a\n"))
                elif name.endswith(".parquet"):
                    self.assertTrue(payload.startswith(b"PAR1"))
                    self.assertTrue(payload.endswith(b"PAR1"))


__all__ = ["S7FixtureManifestTests"]
