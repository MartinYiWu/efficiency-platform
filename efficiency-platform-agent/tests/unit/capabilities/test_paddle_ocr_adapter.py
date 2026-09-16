"""PaddleOCR 注入式适配器测试。"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from efficiency_platform_agent.capabilities.ocr.paddle import PaddleOCRAdapter


class PaddleAdapterTests(unittest.TestCase):
    def test_default_does_not_load_model(self):
        with self.assertRaises(RuntimeError):
            PaddleOCRAdapter().recognize(b"x")

    def test_local_model_factory_is_lazy_and_receives_a_temporary_path(self):
        calls = []

        class FakeEngine:
            def predict(self, source):
                calls.append(Path(source).suffix)
                return [{"text": "合成文字"}]

        with TemporaryDirectory() as folder:
            root = Path(folder)
            detection = root / "det"
            recognition = root / "rec"
            detection.mkdir()
            recognition.mkdir()
            (detection / "inference.yml").write_text("本地模型占位")
            (recognition / "inference.yml").write_text("本地模型占位")
            adapter = PaddleOCRAdapter.from_local_models(detection, recognition)
            self.assertEqual(calls, [])
            adapter.engine_factory = lambda: FakeEngine()
            result = adapter.recognize(b"synthetic-image")

        self.assertEqual(result, [{"text": "合成文字"}])
        self.assertEqual(calls, [".png"])

    def test_local_model_directories_are_required(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ValueError):
                PaddleOCRAdapter.from_local_models(root / "missing", root / "missing2")

    def test_empty_local_model_directories_are_rejected(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            detection = root / "det"
            recognition = root / "rec"
            detection.mkdir()
            recognition.mkdir()
            with self.assertRaisesRegex(
                ValueError, "PADDLE_LOCAL_MODEL_FILES_REQUIRED"
            ):
                PaddleOCRAdapter.from_local_models(detection, recognition)


__all__ = ["PaddleAdapterTests"]
