"""PaddleOCR 注入边界；默认不加载模型。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any


class PaddleOCRAdapter:
    """将 OCR 引擎注入适配器，避免导入时下载模型。"""

    def __init__(self, engine: Any = None, engine_factory: Any = None) -> None:
        self.engine = engine
        self.engine_factory = engine_factory

    @classmethod
    def from_local_models(
        cls,
        detection_model_dir: str | Path,
        recognition_model_dir: str | Path,
        *,
        lang: str = "ch",
    ) -> PaddleOCRAdapter:
        """创建只使用本地模型目录的 OCR 适配器，不允许自动下载模型。"""
        detection = Path(detection_model_dir).resolve()
        recognition = Path(recognition_model_dir).resolve()
        if not detection.is_dir() or not recognition.is_dir():
            raise ValueError("PADDLE_LOCAL_MODEL_DIRECTORY_INVALID")
        if not any(item.is_file() for item in detection.iterdir()) or not any(
            item.is_file() for item in recognition.iterdir()
        ):
            raise ValueError("PADDLE_LOCAL_MODEL_FILES_REQUIRED")
        if not isinstance(lang, str) or not lang.strip():
            raise ValueError("PADDLE_LANGUAGE_INVALID")

        def factory() -> Any:
            from paddleocr import PaddleOCR  # type: ignore[import-untyped]

            return PaddleOCR(
                text_detection_model_dir=str(detection),
                text_recognition_model_dir=str(recognition),
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                lang=lang,
            )

        return cls(engine_factory=factory)

    def recognize(self, content: bytes) -> Any:
        if not isinstance(content, bytes) or not content:
            raise ValueError("PADDLE_CONTENT_INVALID")
        if self.engine is not None:
            return self.engine(content)
        if self.engine_factory is None:
            raise RuntimeError("PADDLE_OCR_NOT_CONFIGURED")
        self.engine = self.engine_factory()
        predict = getattr(self.engine, "predict", None)
        if not callable(predict):
            raise TypeError("PADDLE_ENGINE_INVALID")
        with tempfile.TemporaryDirectory(prefix="agent-paddle-") as folder:
            source = Path(folder) / "source.png"
            source.write_bytes(content)
            return predict(str(source))


__all__ = ["PaddleOCRAdapter"]
