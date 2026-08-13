from __future__ import annotations

import io
import threading

from copilot.config import Settings
from copilot.domain.models import OcrBlock, OcrResult, RawCapture
from copilot.ocr.postprocess import build_result, perceptual_hash


class RapidOcrService:
    """OCR local via RapidOCR (ONNX, instalavel por pip, roda em CPU)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine = None
        self._lock = threading.Lock()

    def _get_engine(self):
        with self._lock:
            if self._engine is None:
                from rapidocr_onnxruntime import RapidOCR

                self._engine = RapidOCR()
            return self._engine

    def run(self, capture: RawCapture) -> OcrResult:
        import numpy as np
        from PIL import Image

        image = Image.open(io.BytesIO(capture.png)).convert("RGB")
        # Upscale 2x melhora muito a leitura de fontes pequenas de UI
        if image.width < 2000:
            image = image.resize((image.width * 2, image.height * 2), Image.LANCZOS)
            scale = 2.0
        else:
            scale = 1.0

        result, _ = self._get_engine()(np.array(image))
        blocks: list[OcrBlock] = []
        for entry in result or []:
            box, text, confidence = entry[0], entry[1], float(entry[2])
            xs = [p[0] / scale for p in box]
            ys = [p[1] / scale for p in box]
            blocks.append(
                OcrBlock(
                    text=str(text),
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                    confidence=confidence,
                )
            )

        return build_result(
            blocks,
            min_confidence=self._settings.ocr_min_confidence,
            image_hash=perceptual_hash(capture.png),
            window_title=capture.window_title,
        )
