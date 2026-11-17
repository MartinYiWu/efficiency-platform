"""只使用部署时已落盘权重的Paddle OCR与本地PDF渲染。"""

import io
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Protocol

from efficiency_platform_agent.capabilities.ocr.paddle import PaddleOCRAdapter
from efficiency_platform_agent.contracts.hr import Block


class OcrAdapter(Protocol):
    def recognize(self, content: bytes) -> object: ...


class LocalHrOcr:
    def __init__(self, adapter: OcrAdapter) -> None:
        self.adapter = adapter

    def _recognize(self, content: bytes, page: int) -> list[Block]:
        result = self.adapter.recognize(content)
        if not isinstance(result, Iterable):
            raise TypeError("HR_FILE_OCR_RESULT_INVALID")
        blocks: list[Block] = []
        for item in result:
            if not isinstance(item, Mapping):
                raise TypeError("HR_FILE_OCR_RESULT_INVALID")
            texts = item.get("rec_texts", [])
            scores = item.get("rec_scores", [])
            boxes = item.get("rec_boxes", item.get("rec_polys", []))
            if not isinstance(texts, (tuple, list)):
                raise TypeError("HR_FILE_OCR_RESULT_INVALID")
            for index, text in enumerate(texts):
                if not isinstance(text, str) or not text.strip():
                    continue
                bbox = None
                if index < len(boxes):
                    box = boxes[index]
                    if hasattr(box, "tolist"):
                        box = box.tolist()
                    if len(box) == 4 and all(isinstance(x, (int, float)) for x in box):
                        bbox = (
                            float(box[0]),
                            float(box[1]),
                            float(box[2]),
                            float(box[3]),
                        )
                    elif box and all(len(point) == 2 for point in box):
                        bbox = (
                            min(float(p[0]) for p in box),
                            min(float(p[1]) for p in box),
                            max(float(p[0]) for p in box),
                            max(float(p[1]) for p in box),
                        )
                blocks.append(
                    Block(
                        block_id=f"ocr-{page}-{len(blocks) + 1}",
                        text=text,
                        page=page,
                        paragraph=index + 1,
                        bbox=bbox,
                        ocr_quality=float(scores[index])
                        if index < len(scores)
                        else 0.0,
                    )
                )
        return blocks

    def __call__(self, content: bytes) -> list[Block]:
        from PIL import Image

        blocks = []
        if content.startswith(b"%PDF-"):
            import pypdfium2 as pdfium  # type: ignore[import-untyped]

            document = pdfium.PdfDocument(content)
            try:
                if len(document) > 200:
                    raise ValueError("HR_FILE_PDF_LIMIT")
                for index in range(len(document)):
                    page = document[index]
                    try:
                        if page.get_width() * page.get_height() * 4 > 40000000:
                            raise ValueError("HR_FILE_IMAGE_LIMIT")
                        bitmap = page.render(scale=2)
                        try:
                            image = bitmap.to_pil()
                            stream = io.BytesIO()
                            image.save(stream, format="PNG")
                            image.close()
                            blocks.extend(self._recognize(stream.getvalue(), index + 1))
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
            finally:
                document.close()
        else:
            with Image.open(io.BytesIO(content)) as image:
                frames = getattr(image, "n_frames", 1)
                if frames > 200:
                    raise ValueError("HR_FILE_IMAGE_LIMIT")
                for index in range(frames):
                    image.seek(index)
                    if image.width * image.height > 40000000:
                        raise ValueError("HR_FILE_IMAGE_LIMIT")
                    stream = io.BytesIO()
                    image.convert("RGB").save(stream, format="PNG")
                    blocks.extend(self._recognize(stream.getvalue(), index + 1))
        if (
            not blocks
            or len(blocks) > 1000
            or sum(len(b.text) for b in blocks) > 100000
        ):
            raise ValueError("HR_FILE_OCR_RESULT_LIMIT")
        return blocks


def build_local_hr_ocr(
    detection_model_dir: str | Path | None, recognition_model_dir: str | Path | None
) -> LocalHrOcr | None:
    import importlib.util

    if detection_model_dir is None or recognition_model_dir is None:
        return None
    if any(
        importlib.util.find_spec(module) is None
        for module in ("paddleocr", "paddle", "pypdfium2", "PIL")
    ):
        return None
    for directory in (Path(detection_model_dir), Path(recognition_model_dir)):
        if not (directory / "inference.pdiparams").is_file() or not any(
            (directory / name).is_file()
            for name in ("inference.json", "inference.pdmodel")
        ):
            return None
    return LocalHrOcr(
        PaddleOCRAdapter.from_local_models(detection_model_dir, recognition_model_dir)
    )
